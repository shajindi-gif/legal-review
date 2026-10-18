"""支付业务层单元测试：回调幂等 + 套餐自动开通。

不触碰真实第三方与真实 DB —— 用 mock AsyncSession 验证状态流转是否正确。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import DateTime
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import (
    PaymentChannel,
    PaymentStatus,
    PlanTier,
    SubscriptionStatus,
)
from app.core.errors import ValidationError
from app.models.user import Order, Payment, UserPlan
from app.services.payment.providers import CallbackResult, CreateOrderResult, RefundResult
from app.services.payment.service import PaymentService, _channel_order_no


def _payment(**kw) -> Payment:
    defaults = {
        "id": uuid4(),
        "order_id": uuid4(),
        "user_id": uuid4(),
        "amount_cny": 99.0,
        "status": PaymentStatus.PENDING,
        "channel": PaymentChannel.WECHAT,
        "channel_trade_no": "",
        "created_at": datetime.now(UTC),
    }
    defaults.update(kw)
    return Payment(**defaults)


def test_channel_order_no_fits_wechat_limit() -> None:
    """微信 out_trade_no 上限 32 字符：36 位 UUID 会被 PARAM_ERROR 拒绝。"""
    assert len(_channel_order_no(uuid4())) == 32
    assert len(str(uuid4())) == 36  # 说明为何必须转换


def _order(**kw) -> Order:
    defaults = {
        "id": uuid4(),
        "user_id": uuid4(),
        "plan_tier": "pro",
        "amount_cny": 99.0,
        "period_days": 30,
        "status": PaymentStatus.PENDING,
        "payment_channel": PaymentChannel.WECHAT,
        "created_at": datetime.now(UTC),
    }
    defaults.update(kw)
    return Order(**defaults)


def _wechat_provider() -> MagicMock:
    provider = MagicMock()
    provider.create_order = AsyncMock(
        return_value=CreateOrderResult(channel_trade_no="pp_1", pay_type="native")
    )
    return provider


def test_payment_flow_datetime_columns_are_tz_aware() -> None:
    """paid_at / 订阅时间列必须声明 timezone=True。

    DB 列是 timestamptz，若 ORM 声明成无时区 DateTime，SQLAlchemy 会按
    TIMESTAMP WITHOUT TIME ZONE 绑定；写入 datetime.now(UTC) 时 flush 会抛
    "can't subtract offset-naive and offset-aware datetimes"，支付结算直接 500。
    """
    table_cols = [
        Order.__table__.c.paid_at,
        Payment.__table__.c.paid_at,
        UserPlan.__table__.c.started_at,
        UserPlan.__table__.c.expires_at,
        UserPlan.__table__.c.cancelled_at,
    ]
    for col in table_cols:
        assert isinstance(col.type, DateTime), col
        assert col.type.timezone is True, col


@pytest.mark.asyncio
async def test_create_order_reuse_key_includes_channel_and_freshness() -> None:
    """复用键必须含 channel + 未超时：否则跨渠道复用，或复用已失效的二维码。"""
    session = AsyncMock(spec=AsyncSession)
    empty_rows = MagicMock()
    empty_rows.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=empty_rows)
    session.scalar = AsyncMock(return_value=None)
    session.add = MagicMock()
    session.flush = AsyncMock()

    with patch.object(PaymentService, "wx", new_callable=PropertyMock) as mock_wx:
        mock_wx.return_value = _wechat_provider()
        result = await PaymentService(session).create_order(
            uuid4(), "pro", 30, "wechat", pay_type="native"
        )

    assert result["pay_type"] == "native"
    sql = str(session.scalar.await_args.args[0])
    assert "orders.payment_channel" in sql  # ① 复用键含渠道
    assert "orders.created_at >=" in sql  # ② 复用键含未超时约束
    added = [c.args[0] for c in session.add.call_args_list if isinstance(c.args[0], Order)]
    assert len(added) == 1  # 无新鲜单 → 新建


@pytest.mark.asyncio
async def test_create_order_closes_stale_pending_instead_of_reusing() -> None:
    """超时的 pending 单不复用：先关单（含流水）再按新单下单。"""
    session = AsyncMock(spec=AsyncSession)
    stale_order = _order(created_at=datetime.now(UTC) - timedelta(hours=3))
    stale_payment = _payment(order_id=stale_order.id)
    stale_rows = MagicMock()
    stale_rows.scalars.return_value.all.return_value = [stale_order]
    close_rows = MagicMock()
    close_rows.scalars.return_value.all.return_value = [stale_payment]
    session.execute = AsyncMock(side_effect=[stale_rows, close_rows])
    session.scalar = AsyncMock(return_value=None)
    session.add = MagicMock()
    session.flush = AsyncMock()

    with patch.object(PaymentService, "wx", new_callable=PropertyMock) as mock_wx:
        mock_wx.return_value = _wechat_provider()
        await PaymentService(session).create_order(uuid4(), "pro", 30, "wechat", pay_type="native")

    assert stale_order.status == PaymentStatus.CLOSED
    assert stale_payment.status == PaymentStatus.CLOSED


@pytest.mark.asyncio
async def test_close_if_expired_also_closes_pending_payments() -> None:
    """超时关单必须同步关闭 Payment，否则流水长期挂 pending，对账口径错误。"""
    session = AsyncMock(spec=AsyncSession)
    order = _order(created_at=datetime.now(UTC) - timedelta(hours=3))
    payment = _payment(order_id=order.id)
    rows = MagicMock()
    rows.scalars.return_value.all.return_value = [payment]
    session.execute = AsyncMock(return_value=rows)
    session.flush = AsyncMock()

    assert await PaymentService(session).close_if_expired(order) is True
    assert order.status == PaymentStatus.CLOSED
    assert payment.status == PaymentStatus.CLOSED


@pytest.mark.asyncio
async def test_close_if_expired_keeps_fresh_order_open() -> None:
    """未超时的 pending 单不关单。"""
    session = AsyncMock(spec=AsyncSession)
    order = _order(created_at=datetime.now(UTC))

    assert await PaymentService(session).close_if_expired(order) is False
    assert order.status == PaymentStatus.PENDING


@pytest.mark.asyncio
async def test_handle_callback_verify_failed_returns_fail() -> None:
    svc = PaymentService(AsyncMock(spec=AsyncSession))
    result = await svc.handle_callback(PaymentChannel.WECHAT, None, {})
    assert result["status"] == "fail"


@pytest.mark.asyncio
async def test_handle_callback_duplicate_returns_success_without_reactivating() -> None:
    """重复通知：已结算订单再次回调 → 幂等返回成功，不再重复开通套餐。"""
    session = AsyncMock(spec=AsyncSession)
    payment = _payment(status=PaymentStatus.SUCCEEDED, channel_trade_no="txn_1")
    session.scalar = AsyncMock(return_value=payment)
    session.add = MagicMock()
    session.flush = AsyncMock()

    svc = PaymentService(session)
    result = await svc.handle_callback(
        PaymentChannel.WECHAT,
        CallbackResult(
            is_success=True,
            channel_trade_no="txn_1",
            amount_cents=9900,
            paid_at=None,
            raw_callback={},
        ),
        {},
    )
    assert result["status"] == "success"
    session.add.assert_not_called()  # 未重复开通套餐


@pytest.mark.asyncio
async def test_handle_callback_first_time_activates_plan() -> None:
    """首次回调（微信 prepay_id 与 transaction_id 不同）→ out_trade_no 确定性反查并开通套餐。"""
    session = AsyncMock(spec=AsyncSession)
    order_id = uuid4()
    user_id = uuid4()
    payment = _payment(order_id=order_id, user_id=user_id, channel_trade_no="prepay_1")
    order = Order(
        id=order_id,
        user_id=user_id,
        plan_tier="pro",
        amount_cny=99.0,
        period_days=30,
        status=PaymentStatus.PENDING,
        created_at=datetime.now(UTC),
    )

    # scalar 调用顺序：1) 精确交易号匹配→None 2) 订单归属流水→payment 3) 套餐查询→None
    session.scalar = AsyncMock(side_effect=[None, payment, None])
    session.get = AsyncMock(return_value=order)
    added: list = []

    def _add(obj) -> None:
        added.append(obj)

    session.add = MagicMock(side_effect=_add)
    session.flush = AsyncMock()

    svc = PaymentService(session)
    result = await svc.handle_callback(
        PaymentChannel.WECHAT,
        CallbackResult(
            is_success=True,
            channel_trade_no="txn_1",
            amount_cents=9900,
            paid_at="2026-01-01T00:00:00+08:00",
            raw_callback={},
            out_trade_no=order_id.hex,
        ),
        {},
    )
    assert result["status"] == "success"
    assert payment.status == PaymentStatus.SUCCEEDED
    assert payment.channel_trade_no == "txn_1"  # transaction_id 回填，供重复通知幂等命中
    assert order.status == PaymentStatus.SUCCEEDED
    plans = [o for o in added if isinstance(o, UserPlan)]
    assert len(plans) == 1


@pytest.mark.asyncio
async def test_mark_paid_out_trade_no_is_deterministic_across_same_amount_orders() -> None:
    """同渠道同金额的两笔 pending 单：按 out_trade_no 精确归属，绝不串到另一笔。

    回归「channel + 金额 + 30 分钟内」任取一条的模糊匹配：实测曾把一笔微信流水
    结算到别的订单并重复发放权益。
    """
    session = AsyncMock(spec=AsyncSession)
    order_a, order_b = uuid4(), uuid4()
    pay_a = _payment(order_id=order_a, channel_trade_no="prepay_a")
    pay_b = _payment(order_id=order_b, channel_trade_no="prepay_b")
    order = Order(
        id=order_a,
        user_id=pay_a.user_id,
        plan_tier="pro",
        amount_cny=99.0,
        period_days=30,
        status=PaymentStatus.PENDING,
        created_at=datetime.now(UTC),
    )
    # scalar：1) 交易号精确→None 2) (order_a, channel) 归属流水→pay_a 3) 套餐→None
    session.scalar = AsyncMock(side_effect=[None, pay_a, None])
    session.get = AsyncMock(return_value=order)
    session.execute = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()

    result = await PaymentService(session).handle_callback(
        PaymentChannel.WECHAT,
        CallbackResult(
            is_success=True,
            channel_trade_no="txn_a",
            amount_cents=9900,
            paid_at=None,
            raw_callback={},
            out_trade_no=order_a.hex,
        ),
        {},
    )

    assert result["status"] == "success"
    assert pay_a.status == PaymentStatus.SUCCEEDED
    assert pay_b.status == PaymentStatus.PENDING  # 未串到另一笔同金额订单
    assert pay_a.channel_trade_no == "txn_a"
    session.execute.assert_not_called()  # 未走模糊回退


@pytest.mark.asyncio
async def test_mark_paid_ambiguous_fallback_refuses_when_multiple_candidates() -> None:
    """渠道未回传 out_trade_no 且同渠道同金额存在多笔 pending → 一律拒绝，不任取一条。"""
    session = AsyncMock(spec=AsyncSession)
    payment1 = _payment(channel_trade_no="prepay_1")
    payment2 = _payment(channel_trade_no="prepay_2")
    rows = MagicMock()
    rows.scalars.return_value.all.return_value = [payment1, payment2]
    session.scalar = AsyncMock(return_value=None)  # 交易号精确匹配未命中
    session.execute = AsyncMock(return_value=rows)
    session.add = MagicMock()
    session.flush = AsyncMock()

    result = await PaymentService(session).handle_callback(
        PaymentChannel.WECHAT,
        CallbackResult(
            is_success=True,
            channel_trade_no="txn_x",
            amount_cents=9900,
            paid_at=None,
            raw_callback={},
        ),
        {},
    )

    assert result["status"] == "fail"
    assert payment1.status == PaymentStatus.PENDING
    assert payment2.status == PaymentStatus.PENDING
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_mark_paid_fallback_settles_when_single_candidate() -> None:
    """渠道未回传 out_trade_no 时，唯一候选仍可结算（兼容历史/异常情形）。"""
    session = AsyncMock(spec=AsyncSession)
    order_id = uuid4()
    payment = _payment(order_id=order_id, channel_trade_no="prepay_1")
    order = Order(
        id=order_id,
        user_id=payment.user_id,
        plan_tier="pro",
        amount_cny=99.0,
        period_days=30,
        status=PaymentStatus.PENDING,
        created_at=datetime.now(UTC),
    )
    rows = MagicMock()
    rows.scalars.return_value.all.return_value = [payment]
    # scalar：1) 交易号精确→None 2) 套餐→None
    session.scalar = AsyncMock(side_effect=[None, None])
    session.execute = AsyncMock(return_value=rows)
    session.get = AsyncMock(return_value=order)
    session.add = MagicMock()
    session.flush = AsyncMock()

    result = await PaymentService(session).handle_callback(
        PaymentChannel.WECHAT,
        CallbackResult(
            is_success=True,
            channel_trade_no="txn_1",
            amount_cents=9900,
            paid_at=None,
            raw_callback={},
        ),
        {},
    )

    assert result["status"] == "success"
    assert payment.status == PaymentStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_mark_paid_out_trade_no_overrides_stale_trade_no_match() -> None:
    """交易号命中的流水挂在别的订单上（历史脏数据）时，以 out_trade_no 归属为准。

    回归实测：一笔微信流水（交易号已回填）被错挂在支付宝订单下，先按交易号命中
    即会把款项继续结算到错误订单。归属必须以渠道回传的 out_trade_no 为准。
    """
    session = AsyncMock(spec=AsyncSession)
    wrong_order, right_order = uuid4(), uuid4()
    stale = _payment(order_id=wrong_order, channel_trade_no="txn_x", status=PaymentStatus.CLOSED)
    correct = _payment(order_id=right_order, channel_trade_no="prepay_r")
    order = Order(
        id=right_order,
        user_id=correct.user_id,
        plan_tier="pro",
        amount_cny=99.0,
        period_days=30,
        status=PaymentStatus.PENDING,
        created_at=datetime.now(UTC),
    )
    # scalar：1) 交易号命中 stale（未结算）2) 归属订单流水→correct 3) 套餐→None
    session.scalar = AsyncMock(side_effect=[stale, correct, None])
    session.get = AsyncMock(return_value=order)
    session.execute = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()

    result = await PaymentService(session).handle_callback(
        PaymentChannel.WECHAT,
        CallbackResult(
            is_success=True,
            channel_trade_no="txn_x",
            amount_cents=9900,
            paid_at=None,
            raw_callback={},
            out_trade_no=right_order.hex,
        ),
        {},
    )

    assert result["status"] == "success"
    assert correct.status == PaymentStatus.SUCCEEDED  # 归属正确的订单被结算
    assert stale.status == PaymentStatus.CLOSED  # 脏数据未被误结算
    session.execute.assert_not_called()  # 归属已锁定，不再模糊匹配


@pytest.mark.asyncio
async def test_create_order_reuse_hits_already_paid_returns_settled_without_reordering() -> None:
    """复用的 pending 单其实已在渠道侧支付成功 → 直接返回已结算，不再重复下单。

    回归：复用的 out_trade_no 已在渠道完成支付，继续用同号下单会被渠道拒绝
    （微信 400 ORDERPAID → 前端 500）。此时应先补偿查单、命中已支付即返回。
    """
    session = AsyncMock(spec=AsyncSession)
    order = _order(amount_cny=299.0, period_days=30)
    payment = _payment(order_id=order.id, user_id=order.user_id, amount_cny=299.0)
    empty_rows = MagicMock()
    empty_rows.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=empty_rows)
    # scalar：1) 复用单命中 2) 交易号精确→None 3) 归属订单流水→payment 4) 套餐→None
    session.scalar = AsyncMock(side_effect=[order, None, payment, None])
    session.get = AsyncMock(return_value=order)
    session.refresh = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()

    provider = _wechat_provider()
    provider.query_order = AsyncMock(
        return_value=CallbackResult(
            is_success=True,
            channel_trade_no="txn_r",
            amount_cents=29900,
            paid_at="2026-10-18T20:30:11+08:00",
            raw_callback={},
            out_trade_no=order.id.hex,
        )
    )

    with patch.object(PaymentService, "wx", new_callable=PropertyMock) as mock_wx:
        mock_wx.return_value = provider
        result = await PaymentService(session).create_order(
            order.user_id, "pro", 30, "wechat", pay_type="native"
        )

    assert result["status"] == "succeeded"
    assert result["qr_code"] == ""
    assert result["pay_url"] == ""
    provider.create_order.assert_not_awaited()  # 未再调渠道下单
    assert order.status == PaymentStatus.SUCCEEDED


# ============== 退款（显式订单 + 显式金额 + 权益回收）==============

def _refund_provider(refund_cents: int = 29900) -> MagicMock:
    provider = _wechat_provider()
    provider.refund = AsyncMock(
        return_value=RefundResult(
            is_success=True,
            refund_cents=refund_cents,
            channel_refund_no="rf_1",
            raw_response={"status": "SUCCESS"},
        )
    )
    return provider


def _refund_rows(payments: list[Payment]) -> MagicMock:
    rows = MagicMock()
    rows.scalars.return_value.all.return_value = payments
    return rows


@pytest.mark.asyncio
async def test_refund_full_marks_order_refunded_and_revokes_plan() -> None:
    """全额退款：订单置 refunded，套餐权益回收（降回 Free + cancelled）。"""
    session = AsyncMock(spec=AsyncSession)
    order = _order(status=PaymentStatus.SUCCEEDED, amount_cny=299.0)
    plan = UserPlan(
        id=uuid4(),
        user_id=order.user_id,
        tier=PlanTier.PRO,
        status=SubscriptionStatus.ACTIVE,
        quota_daily=-1,
    )
    session.get = AsyncMock(return_value=order)
    session.execute = AsyncMock(return_value=_refund_rows([]))  # 无历史退款
    session.scalar = AsyncMock(return_value=plan)  # 权益回收查询
    session.add = MagicMock()
    session.flush = AsyncMock()

    provider = _refund_provider()
    with patch.object(PaymentService, "wx", new_callable=PropertyMock) as mock_wx:
        mock_wx.return_value = provider
        result = await PaymentService(session).refund_order(
            order.id, 29900, "用户申请退款", operator_id=uuid4()
        )

    assert result["full_refund"] is True
    assert result["refund_cents"] == 29900
    assert order.status == PaymentStatus.REFUNDED
    assert plan.tier == PlanTier.FREE  # 权益已回收
    assert plan.status == SubscriptionStatus.CANCELLED
    assert plan.cancelled_at is not None
    added = [c.args[0] for c in session.add.call_args_list if isinstance(c.args[0], Payment)]
    assert len(added) == 1
    assert added[0].status == PaymentStatus.REFUNDED
    assert added[0].channel_trade_no == "rf_1"  # 渠道退款单号留痕
    provider.refund.assert_awaited_once_with(order.id.hex, 29900, 29900, "用户申请退款")


@pytest.mark.asyncio
async def test_refund_partial_keeps_plan_until_fully_refunded() -> None:
    """部分退款：订单保持已支付，权益不回收，仅落退款流水。"""
    session = AsyncMock(spec=AsyncSession)
    order = _order(status=PaymentStatus.SUCCEEDED, amount_cny=299.0)
    session.get = AsyncMock(return_value=order)
    session.execute = AsyncMock(return_value=_refund_rows([]))
    session.add = MagicMock()
    session.flush = AsyncMock()

    provider = _refund_provider(refund_cents=5000)
    with patch.object(PaymentService, "wx", new_callable=PropertyMock) as mock_wx:
        mock_wx.return_value = provider
        result = await PaymentService(session).refund_order(order.id, 5000, "部分退款")

    assert result["full_refund"] is False
    assert order.status == PaymentStatus.SUCCEEDED  # 未退清，订单不置 refunded
    session.scalar.assert_not_called()  # 未触发权益回收


@pytest.mark.asyncio
async def test_refund_rejects_non_succeeded_order() -> None:
    """非已支付订单（pending/closed/refunded）一律拒绝退款。"""
    session = AsyncMock(spec=AsyncSession)
    order = _order(status=PaymentStatus.PENDING)
    session.get = AsyncMock(return_value=order)

    with pytest.raises(ValidationError):
        await PaymentService(session).refund_order(order.id, 9900, "退款")
    session.execute.assert_not_called()  # 未查询退款流水，未调渠道


@pytest.mark.asyncio
async def test_refund_rejects_amount_exceeding_paid() -> None:
    """退款金额超出实付 → 拒绝（显式金额校验，不做隐式截断）。"""
    session = AsyncMock(spec=AsyncSession)
    order = _order(status=PaymentStatus.SUCCEEDED, amount_cny=99.0)
    session.get = AsyncMock(return_value=order)
    session.execute = AsyncMock(return_value=_refund_rows([]))

    with pytest.raises(ValidationError):
        await PaymentService(session).refund_order(order.id, 10000, "退款")


@pytest.mark.asyncio
async def test_refund_rejects_second_full_refund() -> None:
    """已全额退过的订单再次全额退款 → 拒绝（可退余额为 0）。"""
    session = AsyncMock(spec=AsyncSession)
    order = _order(status=PaymentStatus.SUCCEEDED, amount_cny=99.0)
    prior_refund = _payment(
        order_id=order.id,
        user_id=order.user_id,
        amount_cny=99.0,
        status=PaymentStatus.REFUNDED,
    )
    session.get = AsyncMock(return_value=order)
    session.execute = AsyncMock(return_value=_refund_rows([prior_refund]))

    provider = _refund_provider()
    with patch.object(PaymentService, "wx", new_callable=PropertyMock) as mock_wx:
        mock_wx.return_value = provider
        with pytest.raises(ValidationError):
            await PaymentService(session).refund_order(order.id, 9900, "重复退款")
    provider.refund.assert_not_awaited()  # 未调渠道发起二次退款