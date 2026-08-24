"""AuthService 单元测试 - bcrypt / JWT / 注册 / 登录 / 刷新。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import jwt
import pytest
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.core.constants import PlanTier, UserRole, UserStatus
from app.core.errors import AuthError, ConflictError, NotFoundError
from app.services.auth_service import (
    AuthService,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


def _make_session_mock() -> MagicMock:
    """构造一个支持 scalar()/get()/flush() 链式调用的 AsyncMock session。"""
    session = MagicMock()
    session.scalar = AsyncMock()
    session.get = AsyncMock()
    session.flush = AsyncMock()
    session.add = MagicMock()
    session.rollback = AsyncMock()
    session.commit = AsyncMock()
    return session


def _decode(token: str) -> dict:
    settings = get_settings()
    return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])


# ============== bcrypt ==============


def test_hash_password_returns_bcrypt_hash() -> None:
    h = hash_password("hello12345")
    assert h.startswith("$2b$") or h.startswith("$2a$")
    assert h != "hello12345"


def test_verify_password_roundtrip() -> None:
    h = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", h) is True


def test_verify_password_wrong() -> None:
    h = hash_password("real-password")
    assert verify_password("wrong-password", h) is False


def test_verify_password_garbage_hash() -> None:
    """非 bcrypt 哈希不应抛异常，返回 False。"""
    assert verify_password("x", "not-a-hash") is False
    assert verify_password("x", "") is False


# ============== JWT ==============


def test_create_and_decode_access_token() -> None:
    uid = uuid4()
    tok = create_access_token(uid, "submitter", "free")
    payload = _decode(tok)
    assert payload["sub"] == str(uid)
    assert payload["role"] == "submitter"
    assert payload["tier"] == "free"
    assert payload["type"] == "access"


def test_create_and_decode_refresh_token() -> None:
    uid = uuid4()
    tok = create_refresh_token(uid)
    payload = _decode(tok)
    assert payload["sub"] == str(uid)
    assert payload["type"] == "refresh"
    assert "role" not in payload
    assert "tier" not in payload


def test_decode_token_expired() -> None:
    settings = get_settings()
    past = datetime.now(UTC) - timedelta(hours=1)
    payload = {
        "sub": str(uuid4()),
        "type": "access",
        "iat": int(past.timestamp()),
        "exp": int(past.timestamp()) + 1,
    }
    expired = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
    with pytest.raises(AuthError, match="过期"):
        decode_token(expired)


def test_decode_token_invalid_signature() -> None:
    bad = jwt.encode({"sub": "x", "type": "access"}, "wrong-secret", algorithm="HS256")
    with pytest.raises(AuthError, match="无效"):
        decode_token(bad)


def test_decode_token_garbage() -> None:
    with pytest.raises(AuthError):
        decode_token("not-a-jwt")


# ============== AuthService.register ==============


@pytest.mark.asyncio
async def test_register_creates_user_and_free_plan() -> None:
    session = _make_session_mock()
    # 1) email 唯一：None；2) username 唯一：None
    session.scalar.side_effect = [None, None]

    svc = AuthService(session)
    user = await svc.register(
        email="alice@example.com",
        password="password123",
        company="ACME",
        real_name="Alice",
    )

    assert user.email == "alice@example.com"
    assert user.username == "alice"
    assert user.role == UserRole.SUBMITTER
    assert user.company == "ACME"
    assert user.status == UserStatus.ACTIVE
    assert verify_password("password123", user.password_hash)

    assert session.add.call_count == 2
    added_objs = [c.args[0] for c in session.add.call_args_list]
    plan_added = [o for o in added_objs if o.__class__.__name__ == "UserPlan"]
    assert len(plan_added) == 1
    assert plan_added[0].tier == PlanTier.FREE
    assert plan_added[0].quota_daily == 3


@pytest.mark.asyncio
async def test_register_email_already_exists() -> None:
    session = _make_session_mock()
    existing = MagicMock()
    existing.email = "bob@example.com"
    session.scalar.side_effect = [existing]

    svc = AuthService(session)
    with pytest.raises(ConflictError, match="已注册"):
        await svc.register(email="bob@example.com", password="password123")
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_register_username_conflict_appends_suffix() -> None:
    session = _make_session_mock()
    # 1) email None；2-4) username 三次冲突；5) 第四次未冲突
    session.scalar.side_effect = [None, MagicMock(), MagicMock(), MagicMock(), None]

    svc = AuthService(session)
    user = await svc.register(email="charlie@example.com", password="password123")
    assert user.username.startswith("charlie")
    assert len(user.username) > len("charlie")


@pytest.mark.asyncio
async def test_register_integrity_error_rolls_back() -> None:
    session = _make_session_mock()
    session.scalar.side_effect = [None, None]
    session.flush.side_effect = IntegrityError("insert", {}, Exception("dup"))

    svc = AuthService(session)
    with pytest.raises(ConflictError, match="冲突"):
        await svc.register(email="dave@example.com", password="password123")
    session.rollback.assert_awaited()


@pytest.mark.asyncio
async def test_register_default_real_name_is_email_local() -> None:
    session = _make_session_mock()
    session.scalar.side_effect = [None, None]
    svc = AuthService(session)
    user = await svc.register(email="edith@example.com", password="password123")
    assert user.real_name == "edith"


# ============== AuthService.authenticate ==============


@pytest.mark.asyncio
async def test_authenticate_success_updates_last_login() -> None:
    session = _make_session_mock()
    user = MagicMock()
    user.password_hash = hash_password("password123")
    user.status = UserStatus.ACTIVE
    user.last_login_at = None
    session.scalar.return_value = user

    svc = AuthService(session)
    got = await svc.authenticate(email="frank@example.com", password="password123")
    assert got is user
    assert got.last_login_at is not None
    session.flush.assert_awaited()


@pytest.mark.asyncio
async def test_authenticate_wrong_email() -> None:
    session = _make_session_mock()
    session.scalar.return_value = None
    svc = AuthService(session)
    with pytest.raises(AuthError, match="邮箱或密码错误"):
        await svc.authenticate(email="ghost@example.com", password="x")


@pytest.mark.asyncio
async def test_authenticate_wrong_password() -> None:
    session = _make_session_mock()
    user = MagicMock()
    user.password_hash = hash_password("right-password")
    user.status = UserStatus.ACTIVE
    session.scalar.return_value = user
    svc = AuthService(session)
    with pytest.raises(AuthError, match="邮箱或密码错误"):
        await svc.authenticate(email="g@example.com", password="wrong-password")


@pytest.mark.asyncio
async def test_authenticate_inactive_account() -> None:
    session = _make_session_mock()
    user = MagicMock()
    user.password_hash = hash_password("password123")
    user.status = "disabled"
    session.scalar.return_value = user
    svc = AuthService(session)
    with pytest.raises(AuthError, match="状态异常"):
        await svc.authenticate(email="h@example.com", password="password123")


# ============== AuthService.issue_tokens / refresh_access ==============


def test_issue_tokens_without_plan_defaults_to_free() -> None:
    user = MagicMock()
    user.id = uuid4()
    user.role = "submitter"
    user.plan = None
    svc = AuthService(MagicMock())
    tokens = svc.issue_tokens(user)
    assert tokens["token_type"] == "bearer"
    assert "access_token" in tokens and "refresh_token" in tokens
    assert tokens["expires_in"] == get_settings().jwt_access_ttl


def test_issue_tokens_uses_plan_tier() -> None:
    user = MagicMock()
    user.id = uuid4()
    user.role = "submitter"
    user.plan = MagicMock()
    user.plan.tier = PlanTier.PRO
    svc = AuthService(MagicMock())
    tokens = svc.issue_tokens(user)
    payload = _decode(tokens["access_token"])
    assert payload["tier"] == "pro"


@pytest.mark.asyncio
async def test_refresh_access_with_valid_refresh_token() -> None:
    session = _make_session_mock()
    uid = uuid4()
    refresh = create_refresh_token(uid)
    user = MagicMock()
    user.id = uid
    user.status = UserStatus.ACTIVE
    user.role = "submitter"
    user.plan = None
    session.get.return_value = user

    svc = AuthService(session)
    tokens = await svc.refresh_access(refresh)
    assert tokens["access_token"] != refresh
    new_payload = _decode(tokens["access_token"])
    assert new_payload["type"] == "access"
    assert new_payload["sub"] == str(uid)


@pytest.mark.asyncio
async def test_refresh_access_rejects_access_token() -> None:
    session = _make_session_mock()
    access = create_access_token(uuid4(), "submitter", "free")
    svc = AuthService(session)
    with pytest.raises(AuthError, match="非 refresh"):
        await svc.refresh_access(access)


@pytest.mark.asyncio
async def test_refresh_access_user_not_found() -> None:
    session = _make_session_mock()
    refresh = create_refresh_token(uuid4())
    session.get.return_value = None
    svc = AuthService(session)
    with pytest.raises(NotFoundError):
        await svc.refresh_access(refresh)


@pytest.mark.asyncio
async def test_refresh_access_inactive_account() -> None:
    session = _make_session_mock()
    uid = uuid4()
    refresh = create_refresh_token(uid)
    user = MagicMock()
    user.id = uid
    user.status = "disabled"
    session.get.return_value = user
    svc = AuthService(session)
    with pytest.raises(AuthError, match="状态异常"):
        await svc.refresh_access(refresh)


# ============== AuthService.get_user_by_id / get_user_plan ==============


@pytest.mark.asyncio
async def test_get_user_by_id_found() -> None:
    session = _make_session_mock()
    user = MagicMock()
    session.get.return_value = user
    svc = AuthService(session)
    assert await svc.get_user_by_id(uuid4()) is user


@pytest.mark.asyncio
async def test_get_user_by_id_not_found() -> None:
    session = _make_session_mock()
    session.get.return_value = None
    svc = AuthService(session)
    with pytest.raises(NotFoundError):
        await svc.get_user_by_id(uuid4())


@pytest.mark.asyncio
async def test_get_user_plan_creates_default_when_missing() -> None:
    session = _make_session_mock()
    session.scalar.return_value = None
    svc = AuthService(session)
    plan = await svc.get_user_plan(uuid4())
    assert plan.tier == PlanTier.FREE
    assert plan.quota_daily == 3
    session.add.assert_called()
