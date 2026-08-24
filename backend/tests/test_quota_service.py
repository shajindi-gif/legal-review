"""QuotaService 单元测试 - Free 每日 3 次 / Pro 不限 / 跨日重置。"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.constants import PlanTier, SubscriptionStatus
from app.core.errors import QuotaExceededError
from app.services.quota_service import QuotaService


def _make_session() -> MagicMock:
    session = MagicMock()
    session.scalar = AsyncMock()
    session.flush = AsyncMock()
    session.add = MagicMock()
    return session


def _make_plan(
    *,
    tier: str = PlanTier.FREE,
    quota_daily: int = 3,
    used_today: int = 0,
    quota_reset_date: str | None = None,
    status: str = SubscriptionStatus.ACTIVE,
) -> MagicMock:
    plan = MagicMock()
    plan.tier = tier
    plan.status = status
    plan.quota_daily = quota_daily
    plan.used_today = used_today
    plan.quota_reset_date = quota_reset_date or datetime.now(UTC).strftime("%Y-%m-%d")
    return plan


# ============== get_or_create_plan ==============


@pytest.mark.asyncio
async def test_get_or_create_plan_returns_existing() -> None:
    session = _make_session()
    plan = _make_plan()
    session.scalar.return_value = plan
    svc = QuotaService(session)
    got = await svc.get_or_create_plan(__import__("uuid").uuid4())
    assert got is plan
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_get_or_create_plan_creates_free_default() -> None:
    session = _make_session()
    session.scalar.return_value = None
    svc = QuotaService(session)
    plan = await svc.get_or_create_plan(__import__("uuid").uuid4())
    assert plan.tier == PlanTier.FREE
    assert plan.quota_daily == 3
    assert plan.used_today == 0
    session.add.assert_called_once()
    session.flush.assert_awaited()


# ============== is_unlimited / remaining ==============


def test_is_unlimited_pro_and_enterprise() -> None:
    svc = QuotaService(MagicMock())
    assert svc.is_unlimited(_make_plan(tier=PlanTier.PRO, quota_daily=-1)) is True
    assert svc.is_unlimited(_make_plan(tier=PlanTier.ENTERPRISE, quota_daily=-1)) is True
    assert svc.is_unlimited(_make_plan(tier=PlanTier.FREE, quota_daily=3)) is False


def test_remaining_calculates_correctly() -> None:
    svc = QuotaService(MagicMock())
    assert svc.remaining(_make_plan(quota_daily=3, used_today=0)) == 3
    assert svc.remaining(_make_plan(quota_daily=3, used_today=1)) == 2
    assert svc.remaining(_make_plan(quota_daily=3, used_today=3)) == 0
    assert svc.remaining(_make_plan(quota_daily=3, used_today=5)) == 0  # 不为负


def test_remaining_unlimited_returns_minus_one() -> None:
    svc = QuotaService(MagicMock())
    assert svc.remaining(_make_plan(quota_daily=-1, used_today=100)) == -1


# ============== check_quota ==============


@pytest.mark.asyncio
async def test_check_quota_free_under_limit_passes() -> None:
    session = _make_session()
    plan = _make_plan(quota_daily=3, used_today=0)
    session.scalar.return_value = plan
    svc = QuotaService(session)
    got = await svc.check_quota(__import__("uuid").uuid4())
    assert got is plan


@pytest.mark.asyncio
async def test_check_quota_free_at_limit_raises() -> None:
    session = _make_session()
    plan = _make_plan(quota_daily=3, used_today=3)
    session.scalar.return_value = plan
    svc = QuotaService(session)
    with pytest.raises(QuotaExceededError, match="已用尽"):
        await svc.check_quota(__import__("uuid").uuid4())


@pytest.mark.asyncio
async def test_check_quota_pro_unlimited_passes() -> None:
    session = _make_session()
    plan = _make_plan(tier=PlanTier.PRO, quota_daily=-1, used_today=1000)
    session.scalar.return_value = plan
    svc = QuotaService(session)
    got = await svc.check_quota(__import__("uuid").uuid4())
    assert got is plan


# ============== consume ==============


@pytest.mark.asyncio
async def test_consume_increments_used_today_for_free() -> None:
    session = _make_session()
    plan = _make_plan(quota_daily=3, used_today=1)
    session.scalar.return_value = plan
    svc = QuotaService(session)
    got = await svc.consume(__import__("uuid").uuid4())
    assert got.used_today == 2
    session.flush.assert_awaited()


@pytest.mark.asyncio
async def test_consume_does_not_increment_for_pro() -> None:
    session = _make_session()
    plan = _make_plan(tier=PlanTier.PRO, quota_daily=-1, used_today=50)
    session.scalar.return_value = plan
    svc = QuotaService(session)
    got = await svc.consume(__import__("uuid").uuid4())
    assert got.used_today == 50  # 不变


@pytest.mark.asyncio
async def test_consume_over_limit_raises() -> None:
    session = _make_session()
    plan = _make_plan(quota_daily=3, used_today=3)
    session.scalar.return_value = plan
    svc = QuotaService(session)
    with pytest.raises(QuotaExceededError):
        await svc.consume(__import__("uuid").uuid4())


# ============== 跨日重置 ==============


@pytest.mark.asyncio
async def test_consume_resets_used_today_when_date_changed() -> None:
    session = _make_session()
    plan = _make_plan(quota_daily=3, used_today=3, quota_reset_date="2000-01-01")
    session.scalar.return_value = plan
    svc = QuotaService(session)
    got = await svc.consume(__import__("uuid").uuid4())
    # 跨天 → 重置为 0 → consume 后 used_today=1
    assert got.used_today == 1
    assert got.quota_reset_date == datetime.now(UTC).strftime("%Y-%m-%d")


@pytest.mark.asyncio
async def test_consume_does_not_reset_on_same_day() -> None:
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    session = _make_session()
    plan = _make_plan(quota_daily=3, used_today=1, quota_reset_date=today)
    session.scalar.return_value = plan
    svc = QuotaService(session)
    got = await svc.consume(__import__("uuid").uuid4())
    assert got.used_today == 2  # 不重置
    assert got.quota_reset_date == today


# ============== get_status ==============


@pytest.mark.asyncio
async def test_get_status_free_shape() -> None:
    session = _make_session()
    plan = _make_plan(quota_daily=3, used_today=1)
    session.scalar.return_value = plan
    svc = QuotaService(session)
    status = await svc.get_status(__import__("uuid").uuid4())
    assert status["tier"] == "free"
    assert status["quota_daily"] == 3
    assert status["used_today"] == 1
    assert status["remaining"] == 2
    assert status["unlimited"] is False
    assert "reset_date" in status


@pytest.mark.asyncio
async def test_get_status_pro_shape() -> None:
    session = _make_session()
    plan = _make_plan(tier=PlanTier.PRO, quota_daily=-1, used_today=100)
    session.scalar.return_value = plan
    svc = QuotaService(session)
    status = await svc.get_status(__import__("uuid").uuid4())
    assert status["tier"] == "pro"
    assert status["quota_daily"] == -1
    assert status["remaining"] == -1
    assert status["unlimited"] is True
