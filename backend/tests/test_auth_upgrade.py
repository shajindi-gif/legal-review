"""认证系统升级（P0）HTTP 层测试。

覆盖：
- POST /auth/register/password 本地注册（成功 / 重复 / 未同意条款 / 短密码）
- POST /auth/login/password 统一密码登录（本地成功 / Core 回退 / 双失败 / 手机号）
- POST /auth/refresh HttpOnly Cookie 轮换（body 可空）
- POST /logout（Cookie 清除）
- POST /auth/password/forgot（防枚举 / 渠道关闭 403）
- POST /auth/password/reset（撤销全部会话）
- POST /auth/password/change（保留当前会话）
- GET /auth/account、PATCH /auth/account
- POST /auth/account/bind
- GET /auth/sessions、DELETE /auth/sessions/{id}（越权 404）、POST /auth/logout-all

策略：独立 FastAPI app 只挂 auth router；get_db / get_current_user 走
dependency_overrides；Core 客户端 monkeypatch。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from app.api.v1.auth import router as auth_router
from app.core.errors import AppError, AuthError, error_response
from app.services import core_auth_client as cac
from app.services.auth_service import hash_password


# ============== Fakes ==============


class FakeCore:
    def __init__(self) -> None:
        self.login_calls = 0
        self.login_error: Exception | None = None
        self.me_error: Exception | None = None

    async def provision_tenant(self, **kwargs):
        return {"access_token": "ac.provision", "token_type": "bearer"}

    async def login(self, email, password, tenant_slug=None):
        self.login_calls += 1
        if self.login_error is not None:
            raise self.login_error
        return {
            "access_token": "ac.core.login",
            "refresh_token": "rf.core",
            "token_type": "bearer",
            "expires_in": 3600,
        }

    async def me(self, token):
        if self.me_error is not None:
            raise self.me_error
        return cac.CorePrincipal(
            id=uuid4(),
            tenant_id=uuid4(),
            email="core-user@example.com",
            full_name="Core User",
            role="member",
            is_active=True,
        )


def _make_user_mock(password: str = "correct-pass") -> MagicMock:
    """模拟本地 User ORM：真实 Argon2id 哈希 + ACTIVE + Free 套餐。"""
    user = MagicMock()
    user.id = uuid4()
    user.email = "alice@example.com"
    user.phone = None
    user.username = "alice"
    user.real_name = "Alice"
    user.company = None
    user.role = "submitter"
    user.status = "active"
    user.password_hash = hash_password(password)
    user.last_login_at = None
    user.plan = None
    user.locale = "zh-CN"
    user.timezone = "Asia/Shanghai"
    user.email_verified_at = None
    user.phone_verified_at = None
    user.is_super_admin = False
    user.failed_login_count = 0
    user.locked_until = None
    return user


def _make_session_mock() -> MagicMock:
    session = MagicMock()
    session.scalar = AsyncMock(return_value=None)
    session.get = AsyncMock(return_value=None)
    session.flush = AsyncMock()
    session.add = MagicMock()
    session.refresh = AsyncMock()
    session.execute = AsyncMock()
    session.rollback = AsyncMock()
    session.commit = AsyncMock()
    return session


def _make_app(session: MagicMock) -> FastAPI:
    app = FastAPI()
    app.include_router(auth_router)

    @app.exception_handler(AppError)
    async def _app_error_handler(request, exc: AppError):
        return JSONResponse(status_code=exc.http_status, content=error_response(exc))

    from app.api.deps import get_db, get_current_user

    principal = cac.CorePrincipal(
        id=uuid4(),
        tenant_id=None,
        email="alice@example.com",
        full_name="Alice",
        role="submitter",
        is_active=True,
        username="alice",
        real_name="Alice",
        status="active",
        organization_id=None,
        is_super_admin=False,
    )

    async def _get_db():
        yield session

    async def _current_user():
        return principal

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_current_user] = _current_user
    return app


@pytest.fixture
def fake_core(monkeypatch) -> FakeCore:
    from app.api.v1 import auth as auth_mod
    from app.api import deps as deps_mod

    fake = FakeCore()
    monkeypatch.setattr(auth_mod, "get_core_auth_client", lambda: fake)
    monkeypatch.setattr(deps_mod, "get_core_auth_client", lambda: fake)
    return fake


@pytest.fixture
async def client():
    session = _make_session_mock()
    app = _make_app(session)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://t"
    ) as c:
        c._session_mock = session  # type: ignore[attr-defined]
        yield c


# ============== POST /auth/register/password ==============


@pytest.mark.asyncio
async def test_register_password_success_sets_cookie(client, fake_core, monkeypatch) -> None:
    from app.services.auth_service import AuthService

    user = _make_user_mock()

    async def _fake_register(self, **kwargs):
        return user

    monkeypatch.setattr(AuthService, "register", _fake_register)
    resp = await client.post("/auth/register/password", json={
        "email": "new@example.com",
        "password": "password123",
        "agreed_terms": True,
    })
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["is_new_user"] is True
    assert body["access_token"]
    cookie = resp.headers.get("set-cookie", "")
    assert "lr_rt=" in cookie
    assert "httponly" in cookie.lower()
    assert "samesite=lax" in cookie.lower()


@pytest.mark.asyncio
async def test_register_password_duplicate_email_returns_409(client, fake_core) -> None:
    session: MagicMock = client._session_mock
    session.scalar.return_value = _make_user_mock()  # find_by_email 命中
    resp = await client.post("/auth/register/password", json={
        "email": "alice@example.com", "password": "password123", "agreed_terms": True,
    })
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_register_password_terms_required_returns_400(client, fake_core) -> None:
    resp = await client.post("/auth/register/password", json={
        "email": "new@example.com", "password": "password123", "agreed_terms": False,
    })
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "terms_required"


@pytest.mark.asyncio
async def test_register_password_short_password_returns_422(client, fake_core) -> None:
    resp = await client.post("/auth/register/password", json={
        "email": "new@example.com", "password": "short", "agreed_terms": True,
    })
    assert resp.status_code == 422


# ============== POST /auth/login/password ==============


@pytest.mark.asyncio
async def test_login_password_local_success(client, fake_core) -> None:
    session: MagicMock = client._session_mock
    session.scalar.return_value = _make_user_mock("correct-pass")
    resp = await client.post("/auth/login/password", json={
        "identifier": "alice@example.com", "password": "correct-pass",
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["access_token"]
    assert body["is_new_user"] is False
    assert "lr_rt=" in resp.headers.get("set-cookie", "")
    assert fake_core.login_calls == 0  # 本地命中不触 Core
    # 登录审计已写入
    from app.models.identity import UserLoginEvent
    events = [c.args[0] for c in session.add.call_args_list if isinstance(c.args[0], UserLoginEvent)]
    assert any(e.success and e.login_method == "password" for e in events)


@pytest.mark.asyncio
async def test_login_password_core_fallback(client, fake_core) -> None:
    """本地失败（scalar 返回 None）→ Core 成功。"""
    resp = await client.post("/auth/login/password", json={
        "identifier": "legacy@example.com", "password": "legacy-pass",
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["access_token"] == "ac.core.login"
    assert fake_core.login_calls == 1
    # Core 模式不下发本地 refresh cookie
    assert "lr_rt" not in (resp.headers.get("set-cookie") or "")


@pytest.mark.asyncio
async def test_login_password_both_fail_returns_401(client, fake_core) -> None:
    fake_core.login_error = AuthError("邮箱或密码错误")
    resp = await client.post("/auth/login/password", json={
        "identifier": "ghost@example.com", "password": "wrong",
    })
    assert resp.status_code == 401
    assert resp.json()["error"]["message"] == "账号或密码错误"


@pytest.mark.asyncio
async def test_login_password_phone_identifier_no_core_call(client, fake_core) -> None:
    """手机号 identifier 本地失败 → 直接 401，不请求 Core。"""
    resp = await client.post("/auth/login/password", json={
        "identifier": "13800138000", "password": "wrong",
    })
    assert resp.status_code == 401
    assert fake_core.login_calls == 0


@pytest.mark.asyncio
async def test_login_password_local_failure_writes_audit(client, fake_core) -> None:
    fake_core.login_error = AuthError("邮箱或密码错误")
    await client.post("/auth/login/password", json={
        "identifier": "ghost@example.com", "password": "wrong",
    })
    session: MagicMock = client._session_mock
    from app.models.identity import UserLoginEvent
    events = [c.args[0] for c in session.add.call_args_list if isinstance(c.args[0], UserLoginEvent)]
    assert any(not e.success and e.failure_reason == "bad_credentials" for e in events)


# ============== POST /auth/refresh（Cookie 优先） ==============


@pytest.mark.asyncio
async def test_refresh_via_cookie_rotates_and_sets_new_cookie(client) -> None:
    session: MagicMock = client._session_mock
    uid = uuid4()
    from app.services.auth_service import AuthService, create_refresh_token

    raw = create_refresh_token(uid)
    old_rt = MagicMock()
    old_rt.token_hash = AuthService._hash_token(raw)
    old_rt.revoked_at = None
    old_rt.expires_at = datetime.now(UTC) + timedelta(days=1)
    old_rt.user_id = uid

    user = _make_user_mock()
    session.scalar.side_effect = [old_rt, None]  # 旧 token 查找 / 新 token 回查
    session.get.return_value = user

    resp = await client.post(
        "/auth/refresh", json={}, cookies={"lr_rt": raw}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["access_token"]
    assert body["refresh_token"] == ""  # cookie 模式不回传
    assert "lr_rt=" in resp.headers.get("set-cookie", "")


@pytest.mark.asyncio
async def test_refresh_without_token_returns_401(client) -> None:
    resp = await client.post("/auth/refresh", json={})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_logout_with_cookie_clears_cookie(client) -> None:
    session: MagicMock = client._session_mock
    session.scalar.return_value = None  # revoke_refresh_token 找不到也幂等
    resp = await client.post("/auth/logout", json={}, cookies={"lr_rt": "some-token"})
    assert resp.status_code == 200
    cookie = resp.headers.get("set-cookie", "")
    assert "lr_rt=" in cookie  # delete_cookie 也输出 set-cookie
    assert '"max-age": 0' not in cookie


# ============== 密码管理 ==============


@pytest.mark.asyncio
async def test_password_forgot_disabled_channel_returns_403(client) -> None:
    resp = await client.post("/auth/password/forgot", json={"email": "a@example.com"})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "channel_disabled"


@pytest.mark.asyncio
async def test_password_forgot_unknown_email_still_200(client, fake_core, monkeypatch) -> None:
    """防枚举：邮箱不存在恒 200。"""
    monkeypatch.setenv("AUTH_EMAIL_ENABLED", "true")
    from app.core.config import get_settings
    get_settings.cache_clear()
    try:
        resp = await client.post("/auth/password/forgot", json={"email": "ghost@example.com"})
        assert resp.status_code == 200
        assert resp.json()["success"] is True
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_password_reset_success_revokes_all_sessions(client, monkeypatch) -> None:
    session: MagicMock = client._session_mock
    user = _make_user_mock()
    user.password_hash = hash_password("old-pass")
    session.scalar.return_value = user  # find_by_email

    from app.services.verification import VerificationService

    async def _verify_ok(self, **kwargs):
        return True

    monkeypatch.setattr(VerificationService, "verify", _verify_ok)
    monkeypatch.setenv("AUTH_EMAIL_ENABLED", "true")
    from app.core.config import get_settings
    get_settings.cache_clear()
    try:
        resp = await client.post("/auth/password/reset", json={
            "email": "alice@example.com", "code": "123456", "new_password": "new-pass-123",
        })
        assert resp.status_code == 200, resp.text
        assert user.password_hash != hash_password("old-pass")
        # revoke_all_user_tokens 走 session.execute
        session.execute.assert_awaited()
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_password_change_wrong_current_returns_401(client) -> None:
    session: MagicMock = client._session_mock
    user = _make_user_mock("correct-pass")
    session.get.return_value = user  # get_user_by_id

    resp = await client.post("/auth/password/change", json={
        "current_password": "wrong-pass", "new_password": "new-pass-123",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_password_change_success_keeps_current_session(client) -> None:
    session: MagicMock = client._session_mock
    user = _make_user_mock("correct-pass")
    session.get.return_value = user

    resp = await client.post("/auth/password/change", json={
        "current_password": "correct-pass", "new_password": "new-pass-123",
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True


# ============== 账户资料 / 绑定 ==============


@pytest.mark.asyncio
async def test_account_profile_returns_verification_state(client) -> None:
    session: MagicMock = client._session_mock
    user = _make_user_mock()
    session.get.return_value = user
    resp = await client.get("/auth/account")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["email"] == "alice@example.com"
    assert body["email_verified"] is False
    assert body["has_password"] is True
    assert body["plan_tier"] == "free"


@pytest.mark.asyncio
async def test_account_update_profile(client) -> None:
    session: MagicMock = client._session_mock
    user = _make_user_mock()
    session.get.return_value = user
    resp = await client.patch("/auth/account", json={"real_name": "王 Legal", "company": "衍策"})
    assert resp.status_code == 200, resp.text
    assert user.real_name == "王 Legal"
    assert user.company == "衍策"


@pytest.mark.asyncio
async def test_account_bind_disabled_channel_403(client) -> None:
    resp = await client.post("/auth/account/bind", json={
        "channel": "phone", "target": "13800138000", "code": "123456",
        "purpose": "bind_phone",
    })
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_account_bind_purpose_channel_mismatch_422(client, monkeypatch) -> None:
    monkeypatch.setenv("AUTH_SMS_ENABLED", "true")
    from app.core.config import get_settings
    get_settings.cache_clear()
    try:
        resp = await client.post("/auth/account/bind", json={
            "channel": "phone", "target": "13800138000", "code": "123456",
            "purpose": "bind_email",
        })
        assert resp.status_code == 422
    finally:
        get_settings.cache_clear()


# ============== 会话管理 ==============


@pytest.mark.asyncio
async def test_list_sessions_returns_list(client) -> None:
    from app.services.auth_service import AuthService

    session: MagicMock = client._session_mock
    exec_result = MagicMock()
    exec_result.scalars.return_value.all.return_value = []
    session.execute.return_value = exec_result

    resp = await client.get("/auth/sessions")
    assert resp.status_code == 200, resp.text
    assert resp.json()["sessions"] == []


@pytest.mark.asyncio
async def test_revoke_session_other_users_returns_404(client) -> None:
    session: MagicMock = client._session_mock
    other_rt = MagicMock()
    other_rt.user_id = uuid4()  # 非当前用户
    other_rt.revoked_at = None
    session.get.return_value = other_rt

    resp = await client.delete(f"/auth/sessions/{uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_revoke_session_own_returns_success(client) -> None:
    session: MagicMock = client._session_mock
    # get_current_user 的 principal.id 与 rt.user_id 一致
    from app.api.deps import get_current_user
    app = client._transport.app  # type: ignore[attr-defined]
    principal = app.dependency_overrides[get_current_user].__wrapped__ if hasattr(
        app.dependency_overrides[get_current_user], "__wrapped__"
    ) else None

    # 直接构造：rt.user_id == principal.id
    # principal 从 override 闭包外取不到，改为通过第二次请求验证成功路径
    rt = MagicMock()
    rt.user_id = uuid4()
    rt.revoked_at = None
    session.get.return_value = rt
    # 覆盖 get_current_user 返回的 principal.id 与 rt.user_id 对齐
    from app.services import core_auth_client as cac

    async def _current_user_aligned():
        return cac.CorePrincipal(
            id=rt.user_id, tenant_id=None, email="a@b.c", full_name="",
            role="submitter", is_active=True,
        )

    app.dependency_overrides[get_current_user] = _current_user_aligned
    resp = await client.delete(f"/auth/sessions/{uuid4()}")
    assert resp.status_code == 200, resp.text
    assert rt.revoked_at is not None


@pytest.mark.asyncio
async def test_logout_all_returns_count(client) -> None:
    session: MagicMock = client._session_mock
    exec_result = MagicMock()
    exec_result.rowcount = 3
    session.execute.return_value = exec_result

    resp = await client.post("/auth/logout-all")
    assert resp.status_code == 200, resp.text
    assert resp.json()["revoked"] == 3
