"""统一账号（本地 M0 身份系统）单元测试。

覆盖验证码统一登录/注册、持久化 refresh token 签发 / 轮换 / 撤销。
采用与项目一致的 MagicMock session（无真实 DB），聚焦纯逻辑。
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.constants import UserRole, UserStatus
from app.core.errors import AuthError
from app.models.identity import RefreshToken
from app.services.auth_service import AuthService, create_refresh_token


def _make_session_mock() -> MagicMock:
    session = MagicMock()
    session.scalar = AsyncMock()
    session.get = AsyncMock()
    session.flush = AsyncMock()
    session.add = MagicMock()
    session.refresh = AsyncMock()
    session.execute = AsyncMock()
    session.rollback = AsyncMock()
    session.commit = AsyncMock()
    return session


def _added_objects(session: MagicMock) -> list:
    return [c.args[0] for c in session.add.call_args_list]


# ============== login_or_register_by_identity ==============


@pytest.mark.asyncio
async def test_login_or_register_existing_email_returns_same_user() -> None:
    session = _make_session_mock()
    existing = MagicMock()
    existing.status = UserStatus.ACTIVE
    existing.last_login_at = None
    session.scalar.return_value = existing

    svc = AuthService(session)
    user, is_new = await svc.login_or_register_by_identity(
        channel="email", target="alice@example.com"
    )

    assert user is existing
    assert is_new is False
    assert existing.last_login_at is not None
    session.flush.assert_awaited()


@pytest.mark.asyncio
async def test_login_or_register_new_email_creates_account() -> None:
    session = _make_session_mock()
    session.scalar.side_effect = [None, None]  # email 无 / username 无

    svc = AuthService(session)
    user, is_new = await svc.login_or_register_by_identity(
        channel="email", target="bob@example.com"
    )

    assert is_new is True
    assert user.email == "bob@example.com"
    assert user.username == "bob"
    assert user.password_hash == ""          # 验证码账号无密码
    assert user.role == UserRole.SUBMITTER
    assert user.email_verified_at is not None


@pytest.mark.asyncio
async def test_login_or_register_new_phone_creates_account() -> None:
    session = _make_session_mock()
    session.scalar.side_effect = [None, None]

    svc = AuthService(session)
    user, is_new = await svc.login_or_register_by_identity(
        channel="phone", target="+8613800138000"
    )

    assert is_new is True
    assert user.phone == "+8613800138000"
    assert user.email is None
    assert user.phone_verified_at is not None


@pytest.mark.asyncio
async def test_login_or_register_inactive_rejected() -> None:
    session = _make_session_mock()
    existing = MagicMock()
    existing.status = UserStatus.LOCKED
    session.scalar.return_value = existing

    svc = AuthService(session)
    with pytest.raises(AuthError, match="状态异常"):
        await svc.login_or_register_by_identity(channel="email", target="x@example.com")


# ============== 持久化 refresh token ==============


def test_hash_token_sha256() -> None:
    assert AuthService._hash_token("abc") == hashlib.sha256(b"abc").hexdigest()


@pytest.mark.asyncio
async def test_issue_token_pair_persists_refresh() -> None:
    session = _make_session_mock()
    user = MagicMock()
    user.id = uuid4()
    user.role = "submitter"
    user.plan = None

    svc = AuthService(session)
    pair = await svc.issue_token_pair(user)

    assert pair["token_type"] == "bearer"
    assert pair["access_token"]
    raw = pair["refresh_token"]

    refresh_rows = [o for o in _added_objects(session) if isinstance(o, RefreshToken)]
    assert len(refresh_rows) == 1
    assert refresh_rows[0].token_hash == hashlib.sha256(raw.encode()).hexdigest()


@pytest.mark.asyncio
async def test_refresh_token_pair_rotates() -> None:
    session = _make_session_mock()
    uid = uuid4()
    raw = create_refresh_token(uid)
    old_rt = RefreshToken(
        id=uuid4(),
        user_id=uid,
        token_hash=AuthService._hash_token(raw),
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    user = MagicMock()
    user.id = uid
    user.role = "submitter"
    user.status = UserStatus.ACTIVE
    user.plan = None

    session.scalar.side_effect = [old_rt, None]
    session.get.return_value = user

    svc = AuthService(session)
    pair = await svc.refresh_token_pair(raw)

    assert old_rt.revoked_at is not None
    assert old_rt.revoke_reason == "rotation"
    assert pair["refresh_token"] != raw


@pytest.mark.asyncio
async def test_revoke_all_user_tokens_returns_count() -> None:
    session = _make_session_mock()
    result = MagicMock()
    result.rowcount = 3
    session.execute = AsyncMock(return_value=result)

    svc = AuthService(session)
    n = await svc.revoke_all_user_tokens(uuid4())

    assert n == 3
    session.execute.assert_awaited()