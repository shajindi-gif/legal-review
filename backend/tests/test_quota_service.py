"""QuotaService 单元测试 - Free 累计 2 次体验 / Pro 不限。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.constants import FREE_TRIAL_LIMIT, PlanTier, SubscriptionStatus
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
    quota_daily: int = FREE_TRIAL_LIMIT,
    used_today: int = 0,
    free_trial_used: int = 0,
    free_trial_limit: int = FREE_TRIAL_LIMIT,
    status: str = SubscriptionStatus.ACTIVE,
) -> MagicMock:
    plan = MagicMock()
    plan.tier = tier
    plan.status = status
    plan.quota_daily = quota_daily
    plan.used_today = used_today
    plan.free_trial_used = free_trial_used
    plan.free_trial_limit = free_trial_limit
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
    assert plan.free_trial_used == 0
    assert plan.free_trial_limit == FREE_TRIAL_LIMIT
    session.add.assert_called_once()
    session.flush.assert_awaited()


# ============== is_unlimited / remaining ==============


def test_is_unlimited_pro_and_enterprise() -> None:
    svc = QuotaService(MagicMock())
    assert svc.is_unlimited(_make_plan(tier=PlanTier.PRO, quota_daily=-1)) is True
    assert svc.is_unlimited(_make_plan(tier=PlanTier.ENTERPRISE, quota_daily=-1)) is True
    assert svc.is_unlimited(_make_plan(tier=PlanTier.FREE, quota_daily=2)) is False


def test_remaining_calculates_correctly() -> None:
    svc = QuotaService(MagicMock())
    assert svc.remaining(_make_plan(free_trial_used=0)) == 2
    assert svc.remaining(_make_plan(free_trial_used=1)) == 1
    assert svc.remaining(_make_plan(free_trial_used=2)) == 0
    assert svc.remaining(_make_plan(free_trial_used=5)) == 0  # 不为负


def test_remaining_unlimited_returns_minus_one() -> None:
    svc = QuotaService(MagicMock())
    assert svc.remaining(_make_plan(tier=PlanTier.PRO, quota_daily=-1, free_trial_used=100)) == -1


# ============== check_quota ==============


@pytest.mark.asyncio
async def test_check_quota_free_under_limit_passes() -> None:
    session = _make_session()
    plan = _make_plan(free_trial_used=0)
    session.scalar.return_value = plan
    svc = QuotaService(session)
    got = await svc.check_quota(__import__("uuid").uuid4())
    assert got is plan


@pytest.mark.asyncio
async def test_check_quota_free_at_limit_raises() -> None:
    session = _make_session()
    plan = _make_plan(free_trial_used=2)
    session.scalar.return_value = plan
    svc = QuotaService(session)
    with pytest.raises(QuotaExceededError, match="已用尽"):
        await svc.check_quota(__import__("uuid").uuid4())


@pytest.mark.asyncio
async def test_check_quota_pro_unlimited_passes() -> None:
    session = _make_session()
    plan = _make_plan(tier=PlanTier.PRO, quota_daily=-1, free_trial_used=1000)
    session.scalar.return_value = plan
    svc = QuotaService(session)
    got = await svc.check_quota(__import__("uuid").uuid4())
    assert got is plan


# ============== consume ==============


@pytest.mark.asyncio
async def test_consume_increments_free_trial_used_for_free() -> None:
    session = _make_session()
    plan = _make_plan(free_trial_used=1)
    session.scalar.return_value = plan
    svc = QuotaService(session)
    got = await svc.consume(__import__("uuid").uuid4())
    assert got.free_trial_used == 2
    session.flush.assert_awaited()


@pytest.mark.asyncio
async def test_consume_does_not_increment_for_pro() -> None:
    session = _make_session()
    plan = _make_plan(tier=PlanTier.PRO, quota_daily=-1, free_trial_used=50)
    session.scalar.return_value = plan
    svc = QuotaService(session)
    got = await svc.consume(__import__("uuid").uuid4())
    assert got.free_trial_used == 50  # 不变


@pytest.mark.asyncio
async def test_consume_over_limit_raises() -> None:
    session = _make_session()
    plan = _make_plan(free_trial_used=2)
    session.scalar.return_value = plan
    svc = QuotaService(session)
    with pytest.raises(QuotaExceededError):
        await svc.consume(__import__("uuid").uuid4())


# ============== get_status ==============


@pytest.mark.asyncio
async def test_get_status_free_shape() -> None:
    session = _make_session()
    plan = _make_plan(free_trial_used=1)
    session.scalar.return_value = plan
    svc = QuotaService(session)
    status = await svc.get_status(__import__("uuid").uuid4())
    assert status["tier"] == "free"
    assert status["free_trial_used"] == 1
    assert status["free_trial_limit"] == 2
    assert status["remaining"] == 1
    assert status["unlimited"] is False
    assert "reset_date" in status


@pytest.mark.asyncio
async def test_get_status_pro_shape() -> None:
    session = _make_session()
    plan = _make_plan(tier=PlanTier.PRO, quota_daily=-1, free_trial_used=100)
    session.scalar.return_value = plan
    svc = QuotaService(session)
    status = await svc.get_status(__import__("uuid").uuid4())
    assert status["tier"] == "pro"
    assert status["remaining"] == -1
    assert status["unlimited"] is True