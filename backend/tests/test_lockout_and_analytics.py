"""R2-1 账户锁定 / R2-2 通知组织隔离 / R1-3 task_completed 埋点 的回归测试。

这些用例锁定三处「曾经静默失效」的行为：
- 连续密码错误必须累加并在阈值处写入 locked_until，锁定期间正确密码也拒绝；
- notifications.organization_id 为 NOT NULL，未显式传入时必须按收件人所属组织推导；
- 仅当报告生成节点完成时才写 task_completed 事件，避免激活率口径失真。
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from app.core.constants import (
    FAILED_LOGIN_LOCKOUT_MINUTES,
    MAX_FAILED_LOGIN_ATTEMPTS,
)
from app.core.errors import AuthError
from app.services.analytics_sink import build_task_completed_event
from app.services.auth_service import AuthService, hash_password
from app.services.notification import NotificationService


def _make_user(*, password: str = "correct-pass") -> MagicMock:
    user = MagicMock()
    user.id = uuid4()
    user.email = "alice@example.com"
    user.phone = None
    user.status = "active"
    user.password_hash = hash_password(password)
    user.password_changed_at = None
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = None
    return user


def _make_session() -> MagicMock:
    session = MagicMock()
    session.scalar = AsyncMock(return_value=None)
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    return session


# ============== R2-1 账户锁定 ==============


@pytest.mark.asyncio
async def test_failed_login_increments_count() -> None:
    """单次密码错误：failed_login_count +1，未达阈值不锁定。"""
    user = _make_user()
    session = _make_session()
    session.scalar = AsyncMock(return_value=user)
    svc = AuthService(session)

    with pytest.raises(AuthError):
        await svc.authenticate_by_identifier(
            identifier="alice@example.com", password="wrong-pass"
        )

    assert user.failed_login_count == 1
    assert user.locked_until is None
    session.flush.assert_awaited()


@pytest.mark.asyncio
async def test_failed_login_reaching_threshold_sets_lock() -> None:
    """达到阈值：写入 locked_until（UTC 时区），解锁时间 = now + 锁定时长。"""
    user = _make_user()
    user.failed_login_count = MAX_FAILED_LOGIN_ATTEMPTS - 1
    session = _make_session()
    session.scalar = AsyncMock(return_value=user)
    svc = AuthService(session)

    before = datetime.now(UTC)
    with pytest.raises(AuthError):
        await svc.authenticate_by_identifier(
            identifier="alice@example.com", password="wrong-pass"
        )

    assert user.failed_login_count == MAX_FAILED_LOGIN_ATTEMPTS
    locked_until = user.locked_until
    assert locked_until is not None
    delta = locked_until - before
    assert timedelta(minutes=FAILED_LOGIN_LOCKOUT_MINUTES - 1) < delta < timedelta(
        minutes=FAILED_LOGIN_LOCKOUT_MINUTES + 1
    )


@pytest.mark.asyncio
async def test_locked_account_rejects_correct_password() -> None:
    """锁定期间即使密码正确也拒绝，并返回锁定提示（不得泄露密码是否正确）。"""
    user = _make_user()
    # 模拟数据库驱动返回 naive datetime：应被 _as_utc 归一化后正确比较
    user.locked_until = (datetime.now(UTC) + timedelta(minutes=5)).replace(tzinfo=None)
    session = _make_session()
    session.scalar = AsyncMock(return_value=user)
    svc = AuthService(session)

    with pytest.raises(AuthError) as exc:
        await svc.authenticate_by_identifier(
            identifier="alice@example.com", password="correct-pass"
        )

    assert "锁定" in str(exc.value)
    # 锁定拒绝不计入新的失败次数
    assert user.failed_login_count == 0


@pytest.mark.asyncio
async def test_lock_expired_allows_login_and_resets_counter() -> None:
    """锁定到期后正确密码可登录，并清零 failed_login_count / locked_until。"""
    user = _make_user()
    user.failed_login_count = 3
    user.locked_until = datetime.now(UTC) - timedelta(minutes=1)
    session = _make_session()
    session.scalar = AsyncMock(return_value=user)
    svc = AuthService(session)

    result = await svc.authenticate_by_identifier(
        identifier="alice@example.com", password="correct-pass"
    )

    assert result is user
    assert user.failed_login_count == 0
    assert user.locked_until is None


@pytest.mark.asyncio
async def test_failed_login_flush_error_does_not_break_response() -> None:
    """落库失败也不改变对外响应（仍是「账号或密码错误」），只记日志。"""
    user = _make_user()
    session = _make_session()
    session.scalar = AsyncMock(return_value=user)
    session.flush = AsyncMock(side_effect=RuntimeError("db down"))
    svc = AuthService(session)

    with pytest.raises(AuthError) as exc:
        await svc.authenticate_by_identifier(
            identifier="alice@example.com", password="wrong-pass"
        )

    assert "账号或密码错误" in str(exc.value)


# ============== R2-2 通知 organization_id ==============


@pytest.mark.asyncio
async def test_notification_create_derives_organization_id() -> None:
    """未显式传 organization_id 时，按收件人所属组织推导，避免 NOT NULL 违约。"""
    org_id = uuid4()
    session = _make_session()
    session.scalar = AsyncMock(return_value=org_id)
    svc = NotificationService(session)
    recipient = uuid4()

    notif = await svc.create(
        recipient_id=recipient, kind="task", title="审查完成"
    )

    assert notif.organization_id == org_id
    assert notif.recipient_id == recipient
    session.add.assert_called_once()
    session.flush.assert_awaited()


@pytest.mark.asyncio
async def test_notification_create_prefers_explicit_organization_id() -> None:
    """显式传入 organization_id 时不再回查用户表。"""
    org_id = uuid4()
    session = _make_session()
    svc = NotificationService(session)

    notif = await svc.create(
        recipient_id=uuid4(),
        kind="task",
        title="审查完成",
        organization_id=org_id,
    )

    assert notif.organization_id == org_id
    session.scalar.assert_not_awaited()


# ============== R1-3 task_completed 埋点口径 ==============


def test_task_completed_event_requires_report_generation() -> None:
    """未产出报告不写 task_completed（避免把中途失败算作激活）。"""
    assert (
        build_task_completed_event(
            user_id=uuid4(),
            task_id=uuid4(),
            nodes_completed={"doc_parse", "content_review"},
        )
        is None
    )


def test_task_completed_event_properties() -> None:
    user_id: UUID = uuid4()
    task_id: UUID = uuid4()
    event = build_task_completed_event(
        user_id=user_id,
        task_id=task_id,
        nodes_completed={"report_generation", "human_review"},
    )

    assert event is not None
    assert event.event == "task_completed"
    assert event.user_id == user_id
    assert event.properties["task_id"] == str(task_id)
    assert event.properties["human_review"] is True
    assert event.properties["nodes_completed"] == 2
