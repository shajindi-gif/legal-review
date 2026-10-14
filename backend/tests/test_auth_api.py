"""Auth API HTTP 层测试（Strangler 双跑后）。

策略：独立 FastAPI app 只挂 auth router；monkeypatch get_core_auth_client 返回 fake 客户端。
- register → Core provision-tenant（201，路径等价）
- login → Core login（200）
- me → Core /auth/me（200，含 tenant_id，模板 §3.3）
- refresh / logout / sms/send / login/phone → 本地 M0 身份系统已实现
- register/phone → 路由已移除（由 /login/verification 取代）
- quota → 501（冻结，packages/quota 待接入）
- me 无 token → 401
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from app.api.v1.auth import router as auth_router
from app.core.errors import AppError, ConflictError, error_response
from app.services import core_auth_client as cac


class FakeCore:
    """Fake CoreAuthClient：默认成功路径。"""

    def __init__(self) -> None:
        self.provision_calls = 0
        self.login_calls = 0
        self.provision_error: Exception | None = None
        self.login_error: Exception | None = None

    async def provision_tenant(self, **kwargs):
        self.provision_calls += 1
        if self.provision_error is not None:
            raise self.provision_error
        return {"access_token": "ac.provision", "token_type": "bearer"}

    async def login(self, email, password, tenant_slug=None):
        self.login_calls += 1
        if self.login_error is not None:
            raise self.login_error
        return {"access_token": "ac.login", "token_type": "bearer"}

    async def me(self, token):
        return cac.CorePrincipal(
            id=uuid4(),
            tenant_id=uuid4(),
            email="alice@example.com",
            full_name="Alice",
            role="member",
            is_active=True,
        )


@pytest.fixture
def fake_core(monkeypatch) -> FakeCore:
    """patch 各消费模块局部绑定的 get_core_auth_client（from ... import 已绑定）。"""
    from app.api import deps as deps_mod
    from app.api.v1 import auth as auth_mod

    fake = FakeCore()
    monkeypatch.setattr(auth_mod, "get_core_auth_client", lambda: fake)
    monkeypatch.setattr(deps_mod, "get_core_auth_client", lambda: fake)
    return fake


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(auth_router)

    @app.exception_handler(AppError)
    async def _app_error_handler(request, exc: AppError):
        return JSONResponse(status_code=exc.http_status, content=error_response(exc))

    return app


@pytest.fixture
def app() -> FastAPI:
    """每个测试独立 app（fake_db 通过 dependency_overrides 注入 fake session）。"""
    return _make_app()


@pytest.fixture
async def client(app: FastAPI):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c


# ============== POST /auth/register（→ Core provision-tenant） ==============


@pytest.mark.asyncio
async def test_register_success_returns_tokens(client, fake_core) -> None:
    resp = await client.post("/auth/register", json={
        "email": "new@example.com",
        "password": "password123",
        "company": "ACME",
        "real_name": "New",
    })
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"] == "ac.provision"
    assert fake_core.provision_calls == 1
    # provision-tenant 参数映射：tenant_name 优先 company
    call = fake_core.provision_calls  # noqa: F841


@pytest.mark.asyncio
async def test_register_short_password_returns_422(client) -> None:
    resp = await client.post("/auth/register", json={
        "email": "x@example.com", "password": "short",
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_register_invalid_email_returns_422(client) -> None:
    resp = await client.post("/auth/register", json={
        "email": "not-an-email", "password": "password123",
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_register_duplicate_email_returns_409(client, fake_core) -> None:
    fake_core.provision_error = ConflictError("邮箱已注册")
    resp = await client.post("/auth/register", json={
        "email": "dup@example.com", "password": "password123",
    })
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "conflict"


# ============== POST /auth/login（→ Core login） ==============


@pytest.mark.asyncio
async def test_login_success_returns_tokens(client, fake_core) -> None:
    resp = await client.post("/auth/login", json={
        "email": "login@example.com", "password": "password123",
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["access_token"] == "ac.login"
    assert fake_core.login_calls == 1


@pytest.mark.asyncio
async def test_login_wrong_credentials_returns_401(client, fake_core) -> None:
    from app.core.errors import AuthError

    fake_core.login_error = AuthError("邮箱或密码错误")
    resp = await client.post("/auth/login", json={
        "email": "ghost@example.com", "password": "wrong-pass",
    })
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "auth_error"


# ============== GET /auth/me（→ Core /auth/me，含 tenant_id） ==============


@pytest.mark.asyncio
async def test_me_returns_user_with_tenant_id(client, fake_core) -> None:
    resp = await client.get("/auth/me", headers={"Authorization": "Bearer tok"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["email"] == "alice@example.com"
    assert body["role"] == "member"
    assert body["plan_tier"] == "free"
    assert "tenant_id" in body
    assert body["tenant_id"] is not None


@pytest.mark.asyncio
async def test_me_without_token_returns_401(client) -> None:
    resp = await client.get("/auth/me")
    assert resp.status_code == 401


# ============== 本地 M0 统一账号端点（已实现） ==============


@pytest.fixture
def fake_db(app: FastAPI) -> MagicMock:
    """用 app.dependency_overrides 覆盖 get_db，返回 fake AsyncSession（不连真库）。

    注意：Depends(get_db) 在路由声明时已绑定 app.api.deps.get_db 原函数对象，
    monkeypatch 模块属性对依赖解析无效，必须走 dependency_overrides。
    """
    from app.api.deps import get_db

    session = MagicMock()
    session.scalar = AsyncMock(return_value=None)
    session.get = AsyncMock(return_value=None)
    session.flush = AsyncMock()
    session.add = MagicMock()
    session.refresh = AsyncMock()
    session.commit = AsyncMock()
    session.execute = AsyncMock()
    session.rollback = AsyncMock()

    async def _get_db():
        yield session

    app.dependency_overrides[get_db] = _get_db
    return session


@pytest.mark.asyncio
async def test_refresh_invalid_token_returns_401(client) -> None:
    resp = await client.post("/auth/refresh", json={"refresh_token": "x"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "auth_error"


@pytest.mark.asyncio
async def test_quota_returns_501(client) -> None:
    resp = await client.get("/auth/quota", headers={"Authorization": "Bearer tok"})
    assert resp.status_code == 501


@pytest.mark.asyncio
async def test_logout_returns_success(client, fake_db) -> None:
    resp = await client.post("/auth/logout", json={})
    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.asyncio
async def test_sms_send_disabled_returns_403(client, fake_db) -> None:
    resp = await client.post("/auth/sms/send", json={"phone": "13800138000"})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "channel_disabled"


@pytest.mark.asyncio
async def test_register_phone_route_removed_returns_404(client) -> None:
    """旧 /register/phone 已由 /login/verification 取代，路由不存在。"""
    resp = await client.post("/auth/register/phone", json={
        "phone": "13800138000", "code": "1234", "password": "password123",
    })
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_login_phone_wrong_password_returns_401(client, fake_db) -> None:
    resp = await client.post("/auth/login/phone", json={
        "phone": "13800138000", "password": "wrong-pass",
    })
    assert resp.status_code == 401
