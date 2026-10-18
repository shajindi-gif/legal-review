"""支付业务层单元测试：回调幂等 + 套餐自动开通。

不触碰真实第三方与真实 DB —— 用 mock AsyncSession 验证状态流转是否正确。
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import PaymentChannel, PaymentStatus
from app.models.user import Order, Payment, UserPlan
from app.services.payment.providers import CallbackResult
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