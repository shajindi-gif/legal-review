"""支付业务服务层：建单 / 幂等回调 / 自动开通套餐。

与 Provider 层的职责划分：
- Provider（providers.py）：只跟第三方 API 交互（下单、验签、解密）
- PaymentService（本文件）：DB 事务 + 幂等 + 订单状态流转 + 套餐开通
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.constants import (
    CHANNEL_SCENES,
    FREE_TRIAL_LIMIT,
    PLAN_PRICING_CENTS,
    PLAN_QUOTA_DAILY,
    PaymentChannel,
    PaymentStatus,
    PayScene,
    PlanTier,
    SubscriptionStatus,
)
from app.core.errors import AppError, ValidationError
from app.core.logging import get_logger
from app.models.analytics import AnalyticsEvent
from app.models.user import Order, Payment, UserPlan
from app.services.payment.providers import AlipayProvider, CallbackResult, WechatPayProvider

logger = get_logger("payment.service")

PENDING_TIMEOUT_MINUTES = 120  # pending 订单超 2h 未支付自动关闭（SOP 铁律）


def _channel_order_no(order_id: UUID) -> str:
    """渠道侧订单号：微信 out_trade_no 上限 32 字符（36 位 UUID 会 PARAM_ERROR）。

    统一使用 UUID 的 32 位十六进制形式，下单与查单必须保持一致。
    """
    return order_id.hex


class PaymentService:
    """支付业务服务。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._cfg = get_settings()
        self._wx: WechatPayProvider | None = None
        self._ali: AlipayProvider | None = None

    # ---- 懒加载 Provider（避免未配置时启动报错）----
    @property
    def wx(self) -> WechatPayProvider:
        if self._wx is None:
            if not self._cfg.wxpay_enabled:
                raise AppError(code="wxpay_disabled", message="微信支付未启用")
            self._wx = WechatPayProvider()
        return self._wx

    @property
    def ali(self) -> AlipayProvider:
        if self._ali is None:
            if not self._cfg.alipay_enabled:
                raise AppError(code="alipay_disabled", message="支付宝未启用")
            self._ali = AlipayProvider()
        return self._ali

    # ---- 建单 ----
    async def create_order(
        self,
        user_id: UUID,
        plan_tier: str,
        period_days: int,
        channel: str,
        pay_type: str = "native",
        openid: str = "",
        client_ip: str = "",
    ) -> dict:
        """创建订单 + 调用渠道下单，返回支付凭据（二维码 / 跳转 URL / JSAPI 参数）。

        幂等：同一 user + plan_tier + period_days + channel 且未超时的 pending 订单复用。
        """
        if plan_tier not in PLAN_PRICING_CENTS:
            raise ValidationError(f"不支持的套餐: {plan_tier}")
        if period_days not in PLAN_PRICING_CENTS[plan_tier]:
            options = list(PLAN_PRICING_CENTS[plan_tier].keys())
            raise ValidationError(f"不支持的周期: {period_days} 天（可选: {options}）")
        if channel not in (PaymentChannel.WECHAT, PaymentChannel.ALIPAY):
            raise ValidationError(f"不支持的支付渠道: {channel}")

        # 场景校验 + 默认（微信默认 native，支付宝默认 page）
        valid_scenes = {s.value for s in CHANNEL_SCENES[PaymentChannel(channel)]}
        if not pay_type:
            pay_type = PayScene.NATIVE if channel == PaymentChannel.WECHAT else PayScene.PAGE
        if pay_type not in valid_scenes:
            raise ValidationError(
                f"渠道 {channel} 不支持的支付场景: {pay_type}（可选: {sorted(valid_scenes)}）"
            )

        amount_cents = PLAN_PRICING_CENTS[plan_tier][period_days]

        # 幂等：复用键必须与「渠道 + 时限」一致。
        # ① 只复用同 user + plan + period + channel 的 pending 单；
        #    此前缺 channel，导致同一订单混挂 alipay / wechat 两条流水。
        # ② 只复用未超时的单；超时单先关闭再新建，否则会把失效的二维码发给用户。
        cutoff = datetime.now(UTC) - timedelta(minutes=PENDING_TIMEOUT_MINUTES)
        stale = await self._session.execute(
            select(Order).where(
                Order.user_id == user_id,
                Order.plan_tier == plan_tier,
                Order.period_days == period_days,
                Order.payment_channel == channel,
                Order.status == PaymentStatus.PENDING,
                Order.created_at < cutoff,
            )
        )
        for old in stale.scalars().all():
            await self._close_order(old)

        existing = await self._session.scalar(
            select(Order).where(
                Order.user_id == user_id,
                Order.plan_tier == plan_tier,
                Order.period_days == period_days,
                Order.payment_channel == channel,
                Order.status == PaymentStatus.PENDING,
                Order.created_at >= cutoff,
            )
        )
        if existing is not None:
            # 复用旧订单，重新下单（二维码 / 跳转 URL 会过期）。
            # 先补偿查单：若该单其实已在渠道侧支付成功（回调 / 轮询尚未落库），
            # 继续用已支付的 out_trade_no 下单会被渠道拒绝（微信 400 ORDERPAID →
            # 前端 500），故命中已支付时直接返回已结算，不再下单。
            existing = await self.query_and_sync_order(existing)
            if existing.status != PaymentStatus.PENDING:
                return {
                    "order_id": str(existing.id),
                    "order_no": _channel_order_no(existing.id),
                    "pay_type": pay_type,
                    "qr_code": "",
                    "pay_url": "",
                    "jsapi_params": {},
                    "amount_cents": amount_cents,
                    "channel": channel,
                    "status": str(existing.status),
                }
            order = existing
        else:
            order = Order(
                id=uuid.uuid4(),
                user_id=user_id,
                plan_tier=plan_tier,
                amount_cny=amount_cents / 100,
                period_days=period_days,
                status=PaymentStatus.PENDING,
                payment_channel=channel,
            )
            self._session.add(order)
            await self._session.flush()

        order_no = _channel_order_no(order.id)

        # 调用渠道下单
        notify_path = (
            self._cfg.wxpay_notify_path
            if channel == PaymentChannel.WECHAT
            else self._cfg.alipay_notify_path
        )
        notify_url = f"{self._cfg.public_base_url}{notify_path}"
        description = f"法律审查{plan_tier.upper()}套餐-{period_days}天"

        if channel == PaymentChannel.WECHAT:
            result = await self.wx.create_order(
                order_no, amount_cents, description, notify_url,
                pay_type=pay_type, openid=openid, client_ip=client_ip,
            )
        else:
            base = self._cfg.alipay_return_url or f"{self._cfg.public_base_url}/pricing"
            sep = "&" if "?" in base else "?"
            return_url = f"{base}{sep}order_id={order.id}"
            result = await self.ali.create_order(
                order_no, amount_cents, description, notify_url,
                pay_type=pay_type, return_url=return_url,
            )

        # 记录支付流水
        payment = Payment(
            id=uuid.uuid4(),
            order_id=order.id,
            user_id=user_id,
            amount_cny=amount_cents / 100,
            status=PaymentStatus.PENDING,
            channel=channel,
            channel_trade_no=result.channel_trade_no,
        )
        self._session.add(payment)
        await self._session.flush()

        return {
            "order_id": str(order.id),
            "order_no": order_no,
            "pay_type": result.pay_type,
            "qr_code": result.qr_code,
            "pay_url": result.pay_url,
            "jsapi_params": result.jsapi_params,
            "amount_cents": amount_cents,
            "channel": channel,
            "status": str(order.status),
        }

    # ---- 回调处理（微信 / 支付宝通用）----
    async def handle_callback(
        self,
        channel: str,
        verify_result: CallbackResult | None,
        raw_callback: dict,
    ) -> dict:
        """处理支付回调：验签 → 幂等 → 更新订单 → 开通套餐。

        返回 {"status": "success" | "fail", "message": "..."}
        """
        if verify_result is None:
            logger.warning("payment_callback_verify_failed", channel=channel)
            return {"status": "fail", "message": "验签失败"}

        if not verify_result.is_success:
            logger.info("payment_callback_not_success", channel=channel, raw=raw_callback)
            return {"status": "success", "message": "非成功状态，忽略"}

        return await self._mark_paid(channel, verify_result, raw_callback)

    # ---- 支付成功的原子核销（回调 / 主动查单共用，防双发）----
    async def _mark_paid(
        self,
        channel: str,
        verify_result: CallbackResult,
        raw_callback: dict,
    ) -> dict:
        """幂等结算一笔支付：命中订单 → 更新状态 → 开通套餐。

        三条入口（微信回调 / 支付宝回调 / 主动查单补偿）共用本方法，
        保证同一渠道交易号只会开通一次套餐。
        """
        if not verify_result.is_success:
            return {"status": "success", "message": "非成功状态，忽略"}

        # ---- 幂等优先：按渠道交易号精确查找「已结算」流水 ----
        # 首次成功会把微信 transaction_id / 支付宝 trade_no 回填到
        # payment.channel_trade_no；重复通知据此命中已结算订单，避免被误判为
        # "未找到订单"返回 FAIL（否则微信/支付宝会无限重试）。
        payment: Payment | None = None
        # out_trade_no 是否已确定订单归属；锁定后不再做模糊匹配。
        attribution_locked = False
        if verify_result.channel_trade_no:
            payment = await self._session.scalar(
                select(Payment).where(
                    Payment.channel == channel,
                    Payment.channel_trade_no == verify_result.channel_trade_no,
                )
            )
            if payment is not None and payment.status == PaymentStatus.SUCCEEDED:
                logger.info(
                    "payment_duplicate",
                    channel=channel,
                    trade_no=verify_result.channel_trade_no,
                )
                return {"status": "success", "message": "已处理（重复通知）"}

        # ---- 按 out_trade_no 确定性还原订单归属（权威依据）----
        # out_trade_no 即下单时写入的 order.id.hex，渠道原样回传，可唯一还原订单。
        # 此前用「渠道 + 金额 + 30 分钟内」任取一条 pending 流水，同一窗口出现多笔
        # 同渠道同金额订单时会串号（实测把一笔微信流水结算到了别的订单并重复发放权益）。
        # 注意：① 命中的「未结算」流水不可作为归属依据——历史脏数据里可能出现流水
        # 挂在别的订单上（实测：一笔微信流水挂在支付宝订单下）；故以 out_trade_no 为准。
        if verify_result.out_trade_no:
            order = await self._resolve_order_by_out_trade_no(verify_result.out_trade_no)
            if order is not None:
                attribution_locked = True
                if order.status == PaymentStatus.SUCCEEDED:
                    logger.info("payment_duplicate_order", order_id=str(order.id))
                    return {"status": "success", "message": "已处理（订单已结算）"}
                payment = await self._session.scalar(
                    select(Payment)
                    .where(
                        Payment.order_id == order.id,
                        Payment.channel == channel,
                    )
                    .order_by(Payment.created_at.desc())
                )

        # ---- 兜底：仅唯一候选时才按金额 + 时间匹配（兼容渠道未回传 out_trade_no）----
        if payment is None and not attribution_locked:
            paid_at_min = datetime.now(UTC) - timedelta(minutes=30)
            rows = await self._session.execute(
                select(Payment).where(
                    Payment.channel == channel,
                    Payment.status == PaymentStatus.PENDING,
                    Payment.amount_cny == verify_result.amount_cents / 100,
                    Payment.created_at >= paid_at_min,
                )
            )
            candidates = list(rows.scalars().all())
            if len(candidates) == 1:
                payment = candidates[0]
            elif len(candidates) > 1:
                logger.error(
                    "payment_ambiguous_match",
                    channel=channel,
                    amount=verify_result.amount_cents,
                    candidates=len(candidates),
                )
                return {"status": "fail", "message": "订单归属不唯一，拒绝结算"}

        if payment is None:
            logger.error(
                "payment_order_not_found",
                channel=channel,
                amount=verify_result.amount_cents,
                out_trade_no=verify_result.out_trade_no,
            )
            return {"status": "fail", "message": "未找到对应订单"}

        # 并发防御：极端并发下已被另一请求处理
        if payment.status == PaymentStatus.SUCCEEDED:
            return {"status": "success", "message": "已处理"}

        # 金额核对：渠道成交金额必须与订单一致，防止结算到金额不符的订单
        expected_cents = int(round(float(payment.amount_cny) * 100))
        if verify_result.amount_cents and verify_result.amount_cents != expected_cents:
            logger.error(
                "payment_amount_mismatch",
                channel=channel,
                order_id=str(payment.order_id),
                expected_cents=expected_cents,
                got_cents=verify_result.amount_cents,
            )
            return {"status": "fail", "message": "支付金额与订单不一致"}

        # 更新 payment + order
        payment.status = PaymentStatus.SUCCEEDED
        payment.channel_trade_no = verify_result.channel_trade_no or payment.channel_trade_no
        payment.paid_at = datetime.now(UTC)
        payment.raw_callback = raw_callback

        order = await self._session.get(Order, payment.order_id)
        if order is None:
            logger.error("payment_order_missing", payment_id=str(payment.id))
            return {"status": "fail", "message": "订单不存在"}

        order.status = PaymentStatus.SUCCEEDED
        order.payment_no = verify_result.channel_trade_no
        order.paid_at = datetime.now(UTC)

        # 自动开通套餐
        await self._activate_plan(order.user_id, order.plan_tier, order.period_days)

        await self._session.flush()
        logger.info(
            "payment_success",
            order_id=str(order.id),
            user_id=str(order.user_id),
            plan_tier=order.plan_tier,
            period_days=order.period_days,
        )

        # 商业化埋点：order_paid（best-effort，任何异常绝不影响支付主流程）
        try:
            self._session.add(
                AnalyticsEvent(
                    user_id=order.user_id,
                    event="order_paid",
                    properties={
                        "order_id": str(order.id),
                        "amount_cents": verify_result.amount_cents,
                        "plan_tier": order.plan_tier,
                        "channel": channel,
                    },
                )
            )
        except Exception as e:
            logger.warning("analytics_order_paid_failed", error=str(e))

        return {"status": "success", "message": "OK"}

    async def _resolve_order_by_out_trade_no(self, out_trade_no: str) -> Order | None:
        """由渠道商户订单号确定性还原订单归属。

        out_trade_no 在下单时写入为 order.id.hex（见 _channel_order_no），渠道原样回传，
        故可唯一还原订单，替代此前的「渠道 + 金额 + 时间」模糊匹配。
        """
        try:
            order_id = UUID(hex=out_trade_no)
        except (ValueError, AttributeError, TypeError):
            logger.error("payment_out_trade_no_unparsable", out_trade_no=out_trade_no)
            return None
        return await self._session.get(Order, order_id)

    # ---- 主动查单补偿（回调可能不来）+ 超时关单 ----
    async def query_and_sync_order(self, order: Order) -> Order:
        """对 pending 订单主动查单（回调缺失时补偿），命中则结算并开通套餐。

        返回同步后的订单对象。
        """
        if order.status != PaymentStatus.PENDING:
            return order

        channel = order.payment_channel
        order_no = _channel_order_no(order.id)
        try:
            if channel == PaymentChannel.WECHAT:
                result = await self.wx.query_order(order_no)
            elif channel == PaymentChannel.ALIPAY:
                result = await self.ali.query_order(order_no)
            else:
                return order
        except AppError:
            return order  # 渠道未启用时不结算
        except Exception as e:  # 查单网络/参数异常不阻断轮询
            logger.warning("payment_query_error", order_id=order_no, error=str(e))
            return order

        if result is not None and result.is_success:
            await self._mark_paid(channel, result, result.raw_callback)
            await self._session.refresh(order)
        return order

    async def _close_order(self, order: Order) -> None:
        """关闭订单，并同步关闭其所有未支付的支付流水。

        此前只改 Order 状态，Payment 仍长期挂 pending，导致对账口径错误。
        """
        order.status = PaymentStatus.CLOSED
        rows = await self._session.execute(
            select(Payment).where(
                Payment.order_id == order.id,
                Payment.status == PaymentStatus.PENDING,
            )
        )
        for p in rows.scalars().all():
            p.status = PaymentStatus.CLOSED
        await self._session.flush()

    async def close_if_expired(self, order: Order) -> bool:
        """pending 订单超过 2h 未支付则关闭（含同步关闭其 pending 流水）。返回是否已关闭。"""
        if order.status != PaymentStatus.PENDING:
            return False
        if (
            order.created_at is not None
            and datetime.now(UTC) - order.created_at > timedelta(minutes=PENDING_TIMEOUT_MINUTES)
        ):
            await self._close_order(order)
            logger.info("payment_order_closed_timeout", order_id=str(order.id))
            return True
        return False

    # ---- 套餐开通 ----
    async def _activate_plan(self, user_id: UUID, plan_tier: str, period_days: int) -> None:
        """开通/续费套餐。

        user_plans.user_id 唯一：每个用户只有一条 plan 记录。
        免费 → 付费 升级在现有记录上就地改为目标 tier 并顺延 expires_at。
        """
        plan = await self._session.scalar(
            select(UserPlan).where(UserPlan.user_id == user_id)
        )
        now = datetime.now(UTC)
        quota_daily = PLAN_QUOTA_DAILY.get(plan_tier, -1)

        if plan is not None:
            # 续费/升级：从当前 expires_at 或 now 开始延长
            base = plan.expires_at if plan.expires_at and plan.expires_at > now else now
            plan.tier = PlanTier(plan_tier)
            plan.status = SubscriptionStatus.ACTIVE
            plan.quota_daily = quota_daily
            plan.period_days = period_days
            plan.started_at = now
            plan.expires_at = base + timedelta(days=period_days)
            # 付费后按 tier 判定不限次数，免费试用计数不再参与配额判断
            logger.info(
                "plan_renewed",
                user_id=str(user_id),
                tier=plan_tier,
                expires_at=plan.expires_at.isoformat(),
            )
        else:
            expires_at = now + timedelta(days=period_days)
            plan = UserPlan(
                id=uuid.uuid4(),
                user_id=user_id,
                tier=plan_tier,
                status="active",
                quota_daily=quota_daily,
                period_days=period_days,
                started_at=now,
                expires_at=expires_at,
                used_today=0,
                free_trial_used=0,
                free_trial_limit=FREE_TRIAL_LIMIT,
                quota_reset_date=now.strftime("%Y-%m-%d"),
            )
            self._session.add(plan)
            logger.info(
                "plan_activated",
                user_id=str(user_id),
                tier=plan_tier,
                expires_at=expires_at.isoformat(),
            )

    # ---- 查询 ----
    async def get_order(self, order_id: UUID) -> Order | None:
        return await self._session.get(Order, order_id)

    async def get_user_orders(self, user_id: UUID, limit: int = 20) -> list[Order]:
        stmt = (
            select(Order)
            .where(Order.user_id == user_id)
            .order_by(Order.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
