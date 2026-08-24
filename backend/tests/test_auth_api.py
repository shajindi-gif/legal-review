"""Auth API HTTP 层测试 - register/login/refresh/me/quota/logout。

策略：独立 FastAPI app 只挂 auth router，dependency_overrides 注入 mock session/user。
- get_db 必须在 app.db.session 和 app.api.deps 两侧都 override（路由两侧都 import 了它）
- AuditService.log 由 conftest autouse fixture 桩成 no-op
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from fastapi.responses import JSONResponse

from app.api import deps as api_deps
from app.api.v1.auth import router as auth_router
from app.core.errors import AppError, error_response
from app.db import session as db_session
from app.services.auth_service import create_access_token, create_refresh_token


def _mock_session() -> MagicMock:
    """对 AuthService/QuotaService 够用的 AsyncMock session。"""
    s = MagicMock()
    s.scalar = AsyncMock()
    s.get = AsyncMock()
    s.flush = AsyncMock()
    s.add = MagicMock()
    s.rollback = AsyncMock()
    s.commit = AsyncMock()
    s.refresh = AsyncMock()
    return s


def _mock_user(
    *,
    user_id=None,
    email: str = "alice@example.com",
    username: str = "alice",
    role: str = "submitter",
    status: str = "active",
    plan=None,
) -> MagicMock:
    u = MagicMock()
    u.id = user_id or uuid4()
    u.email = email
    u.username = username
    u.real_name = username.title()
    u.company = "ACME"
    u.role = role
    u.status = status
    u.password_hash = "hashed"
    u.last_login_at = None
    u.plan = plan
    return u


def _make_app(
    *,
    session: MagicMock | None = None,
    user: MagicMock | None = None,
) -> FastAPI:
    """独立 app + auth router + 两侧 get_db override + 全局 AppError handler。"""
    app = FastAPI()
    app.include_router(auth_router)

    @app.exception_handler(AppError)
    async def _app_error_handler(request, exc: AppError):
        return JSONResponse(status_code=exc.http_status, content=error_response(exc))

    if session is not None:
        async def _get_db():
            yield session
        app.dependency_overrides[db_session.get_db] = _get_db
        app.dependency_overrides[api_deps.get_db] = _get_db
    if user is not None:
        app.dependency_overrides[api_deps.get_current_user] = lambda: user
    return app


# ============== POST /auth/register ==============


@pytest.mark.asyncio
async def test_register_success_returns_tokens() -> None:
    session = _mock_session()
    session.scalar.side_effect = [None, None]  # email/username 唯一

    app = _make_app(session=session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        resp = await c.post("/auth/register", json={
            "email": "new@example.com",
            "password": "password123",
            "company": "ACME",
            "real_name": "New",
        })

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert "access_token" in body and "refresh_token" in body
    assert body["expires_in"] > 0
    # session.add 被调用 User + UserPlan
    assert session.add.call_count == 2


@pytest.mark.asyncio
async def test_register_short_password_returns_422() -> None:
    app = _make_app(session=_mock_session())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        resp = await c.post("/auth/register", json={
            "email": "x@example.com", "password": "short",
        })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_register_invalid_email_returns_422() -> None:
    app = _make_app(session=_mock_session())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        resp = await c.post("/auth/register", json={
            "email": "not-an-email", "password": "password123",
        })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_register_duplicate_email_returns_409() -> None:
    session = _mock_session()
    existing = _mock_user(email="dup@example.com")
    session.scalar.side_effect = [existing]  # email 查重命中
    app = _make_app(session=session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        resp = await c.post("/auth/register", json={
            "email": "dup@example.com", "password": "password123",
        })
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "conflict"


# ============== POST /auth/login ==============


@pytest.mark.asyncio
async def test_login_success_returns_tokens() -> None:
    """绕过 bcrypt：monkey-patch verify_password。"""
    from app.services import auth_service
    session = _mock_session()
    user = _mock_user(email="login@example.com")
    session.scalar.return_value = user

    real_verify = auth_service.verify_password
    auth_service.verify_password = lambda plain, h: plain == "password123"
    try:
        app = _make_app(session=session)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            resp = await c.post("/auth/login", json={
                "email": "login@example.com", "password": "password123",
            })
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "access_token" in body
        # last_login_at 应被更新
        assert user.last_login_at is not None
    finally:
        auth_service.verify_password = real_verify


@pytest.mark.asyncio
async def test_login_wrong_credentials_returns_401() -> None:
    session = _mock_session()
    session.scalar.return_value = None
    app = _make_app(session=session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        resp = await c.post("/auth/login", json={
            "email": "ghost@example.com", "password": "password123",
        })
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "auth_error"


@pytest.mark.asyncio
async def test_login_disabled_account_returns_401() -> None:
    from app.services import auth_service
    session = _mock_session()
    user = _mock_user(email="d@example.com", status="disabled")
    session.scalar.return_value = user
    real_verify = auth_service.verify_password
    auth_service.verify_password = lambda plain, h: True
    try:
        app = _make_app(session=session)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            resp = await c.post("/auth/login", json={
                "email": "d@example.com", "password": "anything",
            })
        assert resp.status_code == 401, resp.text
    finally:
        auth_service.verify_password = real_verify


# ============== POST /auth/refresh ==============


@pytest.mark.asyncio
async def test_refresh_with_valid_refresh_token() -> None:
    session = _mock_session()
    uid = uuid4()
    user = _mock_user(user_id=uid, role="submitter")
    session.get.return_value = user

    refresh = create_refresh_token(uid)
    app = _make_app(session=session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        resp = await c.post("/auth/refresh", json={"refresh_token": refresh})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "access_token" in body
    assert body["access_token"] != refresh


@pytest.mark.asyncio
async def test_refresh_with_access_token_returns_401() -> None:
    session = _mock_session()
    access = create_access_token(uuid4(), "submitter", "free")
    app = _make_app(session=session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        resp = await c.post("/auth/refresh", json={"refresh_token": access})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_with_garbage_returns_401() -> None:
    app = _make_app(session=_mock_session())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        resp = await c.post("/auth/refresh", json={"refresh_token": "not-a-jwt"})
    assert resp.status_code == 401


# ============== GET /auth/me ==============


@pytest.mark.asyncio
async def test_me_returns_user_with_plan() -> None:
    plan = MagicMock()
    plan.tier = "free"
    plan.quota_daily = 3
    plan.used_today = 1
    user = _mock_user(plan=plan, role="submitter")
    app = _make_app(user=user)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        resp = await c.get("/auth/me")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["email"] == "alice@example.com"
    assert body["role"] == "submitter"
    assert body["plan_tier"] == "free"
    assert body["quota_daily"] == 3
    assert body["used_today"] == 1


@pytest.mark.asyncio
async def test_me_without_token_returns_401() -> None:
    """不 override get_current_user → 真实 JWT 校验 → 401。"""
    app = _make_app()  # 无 overrides
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        resp = await c.get("/auth/me")
    assert resp.status_code == 401


# ============== GET /auth/quota ==============


@pytest.mark.asyncio
async def test_quota_returns_status_dict() -> None:
    user = _mock_user()
    session = _mock_session()
    # QuotaService.get_status → 第一次 scalar 返回 None → 创建 plan
    session.scalar.side_effect = [None]
    app = _make_app(session=session, user=user)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        resp = await c.get("/auth/quota")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tier"] == "free"
    assert body["quota_daily"] == 3
    assert body["unlimited"] is False


@pytest.mark.asyncio
async def test_quota_without_token_returns_401() -> None:
    app = _make_app(session=_mock_session())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        resp = await c.get("/auth/quota")
    assert resp.status_code == 401


# ============== POST /auth/logout ==============


@pytest.mark.asyncio
async def test_logout_returns_ok() -> None:
    user = _mock_user()
    app = _make_app(session=_mock_session(), user=user)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        resp = await c.post("/auth/logout")
    assert resp.status_code == 200, resp.text
    assert resp.json()["message"] == "已登出"


@pytest.mark.asyncio
async def test_logout_without_token_returns_401() -> None:
    app = _make_app(session=_mock_session())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        resp = await c.post("/auth/logout")
    assert resp.status_code == 401
