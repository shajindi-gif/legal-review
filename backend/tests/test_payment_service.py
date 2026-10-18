"""支付业务层单元测试：回调幂等 + 套餐自动开通。

不触碰真实第三方与真实 DB —— 用 mock AsyncSession 验证状态流转是否正确。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import PaymentChannel, PaymentStatus
from app.models.user import Order, Payment, UserPlan
from app.services.payment.providers import CallbackResult, CreateOrderResult
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
    """首次回调（微信 prepay_id 与 transaction_id 不同，走金额回退）→ 开通套餐。"""
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

    # scalar 调用顺序：1) 精确交易号匹配→None 2) 金额回退→payment 3) 计划查询→None
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
        ),
        {},
    )
    assert result["status"] == "success"
    assert payment.status == PaymentStatus.SUCCEEDED
    assert payment.channel_trade_no == "txn_1"  # transaction_id 回填，供重复通知幂等命中
    assert order.status == PaymentStatus.SUCCEEDED
    plans = [o for o in added if isinstance(o, UserPlan)]
    assert len(plans) == 1