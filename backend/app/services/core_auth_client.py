"""Core Auth HTTP 客户端 — Strangler 双跑。

legal-review 后端通过本客户端调用 yance-core packages/auth（Core Auth API）。
双跑期：新注册/登录流量只写 Core 新库 yance_core；legal_review 旧库只读保留。

Core 当前仅提供：/auth/bootstrap、/auth/provision-tenant、/auth/login、/auth/me、/tenants/*
（无 refresh / quota / phone / sms，其余由 legal-review 冻结为 501 待 Core 迭代补入）
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

import httpx

from app.core.config import get_settings
from app.core.errors import AppError, AuthError, ConflictError

# Core packages/auth API 前缀（与 Core config.api_v1_prefix 一致）
_CORE_API_PREFIX = "/api/v1"


@dataclass(frozen=True)
class CorePrincipal:
    """Core /auth/me 映射出的请求主体。

    为兼容 legal-review 业务层对 current_user 的属性访问：
    - id / role / organization_id：业务模块（documents/search/notifications/tasks）依赖
    - tenant_id：Core 多租户标识（新增，模板 §3.3 要求 /me 带 tenant_id）
    - organization_id 恒为 None：双跑期 Core 用户在本库无 Organization 记录
    - status 固定 active（Core 校验过 is_active 才签发主体）
    """
    id: UUID
    tenant_id: UUID | None
    email: str | None
    full_name: str
    role: str
    is_active: bool
    username: str = ""
    real_name: str = ""
    company: str | None = None
    status: str = "active"
    organization_id: UUID | None = None
    is_super_admin: bool = False
    last_login_at: Any = None

    def __post_init__(self) -> None:
        email = self.email or ""
        username = self.username or email.split("@")[0] or "user"
        real_name = self.real_name or self.full_name or username.title()
        object.__setattr__(self, "username", username)
        object.__setattr__(self, "real_name", real_name)


class CoreAuthClient:
    """Core Auth API 的异步 HTTP 客户端（无状态，可复用）。"""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = 5.0,
    ) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.core_api_url).rstrip("/")
        self.api_key = api_key or settings.core_api_key
        self.timeout = timeout

    # ---------- 内部 ----------

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """发请求；Core 不可达时映射为 503 AppError，不泄露堆栈。"""
        try:
            # trust_env=False：Core 位于本机 127.0.0.1，禁用系统/环境代理避免走代理导致 502
            async with httpx.AsyncClient(
                base_url=self.base_url, timeout=self.timeout, trust_env=False
            ) as client:
                resp = await client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise AppError(
                code="core_auth_unavailable",
                message=f"认证服务暂不可用: {exc.__class__.__name__}",
                http_status=503,
            ) from exc
        return resp

    @staticmethod
    def _raise_for_status(resp: httpx.Response) -> None:
        if resp.status_code < 400:
            return
        detail = resp.text[:200]
        if resp.status_code == 409:
            raise ConflictError(detail or "资源冲突")
        if resp.status_code in (401, 403):
            raise AuthError(detail or "认证失败")
        raise AppError(
            code="core_auth_error",
            message=f"Core Auth 错误 {resp.status_code}: {detail}",
            http_status=resp.status_code,
        )

    def _auth_headers(self, access_token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {access_token}"}

    # ---------- 业务方法 ----------

    async def login(
        self,
        email: str,
        password: str,
        tenant_slug: str | None = None,
    ) -> dict:
        """登录（Core OAuth2 form）。返回 legal-review TokenResponse 兼容 dict。

        Core 仅签发 access_token（无 refresh_token），refresh_token 置空、expires_in 置 0。
        """
        headers: dict[str, str] = {}
        if tenant_slug:
            headers["X-Tenant-Slug"] = tenant_slug
        resp = await self._request(
            "POST",
            f"{_CORE_API_PREFIX}/auth/login",
            headers=headers,
            data={"username": email, "password": password},
        )
        self._raise_for_status(resp)
        data = resp.json()
        return {
            "access_token": data["access_token"],
            "refresh_token": "",  # Core 暂无 refresh（待迭代）
            "token_type": data.get("token_type", "bearer"),
            "expires_in": 0,  # Core 未返回，置 0（前端勿依赖）
        }

    async def provision_tenant(
        self,
        *,
        tenant_name: str,
        tenant_slug: str,
        owner_email: str,
        owner_name: str,
        owner_password: str,
    ) -> dict:
        """等价旧 register：创建租户 + owner，返回 token。

        email 重复 → Core 409 → ConflictError（旧 register 语义一致）。
        """
        resp = await self._request(
            "POST",
            f"{_CORE_API_PREFIX}/auth/provision-tenant",
            headers={"X-Tenant-Provisioning-Token": self.api_key},
            json={
                "tenant_name": tenant_name,
                "tenant_slug": tenant_slug,
                "owner_email": owner_email,
                "owner_name": owner_name,
                "owner_password": owner_password,
            },
        )
        self._raise_for_status(resp)
        data = resp.json()
        return {
            "access_token": data["access_token"],
            "refresh_token": "",
            "token_type": data.get("token_type", "bearer"),
            "expires_in": 0,
        }

    async def me(self, access_token: str) -> CorePrincipal:
        """当前用户（含 tenant_id）。"""
        resp = await self._request(
            "GET",
            f"{_CORE_API_PREFIX}/auth/me",
            headers=self._auth_headers(access_token),
        )
        self._raise_for_status(resp)
        data = resp.json()
        return CorePrincipal(
            id=UUID(data["id"]),
            tenant_id=UUID(data["tenant_id"]),
            email=data.get("email"),
            full_name=data.get("full_name", ""),
            role=str(data.get("role", "member")),
            is_active=bool(data.get("is_active", True)),
        )


_client: CoreAuthClient | None = None


def get_core_auth_client() -> CoreAuthClient:
    """进程级单例客户端。"""
    global _client
    if _client is None:
        _client = CoreAuthClient()
    return _client
