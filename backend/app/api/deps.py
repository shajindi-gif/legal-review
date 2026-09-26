"""FastAPI 依赖注入 - DB session / Sandbox / 审计 / 鉴权 / 租户上下文。"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import UserStatus
from app.core.errors import AppError, AuthError
from app.db.session import get_db as _get_db
from app.models.user import Organization, User
from app.services.audit import AuditService
from app.services.auth_service import decode_token
from app.services.core_auth_client import CorePrincipal, get_core_auth_client
from app.services.sandbox import SandboxService, get_sandbox
from app.services.tenant import is_super_admin, load_user_org


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """每请求一个 DB session 依赖。"""
    async for s in _get_db():
        yield s


def get_sandbox_dep() -> SandboxService:
    """沙箱服务依赖。"""
    return get_sandbox()


def get_audit_service(session: AsyncSession = Depends(get_db)) -> AuditService:
    """审计服务依赖。"""
    return AuditService(session)


def get_trace_id(request: Request) -> str:
    """从请求头或新生成的 trace_id。"""
    return request.headers.get("X-Trace-Id") or ""


def get_actor(
    request: Request,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    x_user_role: str | None = Header(default=None, alias="X-User-Role"),
) -> dict:
    """从请求头解析 actor（鉴权层未上线前用 header 简化）。

    保留向后兼容：若已通过 JWT 鉴权，X-User-Id / X-User-Role 可由网关注入。
    """
    return {
        "user_id": x_user_id,
        "role": x_user_role,
        "ip": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
    }


# ============== JWT 鉴权 ==============


def _principal_from_local_user(user: User) -> CorePrincipal:
    """本地 User ORM → 兼容业务层的 CorePrincipal。"""
    return CorePrincipal(
        id=user.id,
        tenant_id=None,
        email=user.email,
        full_name=user.real_name,
        role=str(user.role),
        is_active=str(user.status) == str(UserStatus.ACTIVE),
        username=user.username,
        real_name=user.real_name,
        company=user.company,
        status=str(user.status),
        organization_id=user.organization_id,
        is_super_admin=bool(user.is_super_admin),
        last_login_at=user.last_login_at,
    )


async def _try_local_principal(
    token: str, session: AsyncSession
) -> CorePrincipal | None:
    """优先尝试本地 JWT（统一账号系统签发）。非本地 token → 返回 None 回退 Core。"""
    try:
        payload = decode_token(token)
    except AuthError:
        return None
    if payload.get("type") != "access":
        return None
    try:
        user_id = UUID(payload["sub"])
    except (KeyError, TypeError, ValueError):
        return None
    user = await session.get(User, user_id)
    if user is None:
        raise AuthError("登录已失效，请重新登录")
    if str(user.status) != str(UserStatus.ACTIVE):
        raise AuthError("账号状态异常，请联系管理员")
    return _principal_from_local_user(user)


async def get_current_user(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_db),
) -> CorePrincipal:
    """从 Authorization: Bearer <token> 解析当前用户（本地 JWT 优先，Core 回退）。

    流程：
    1. 提取 Bearer token
    2. 尝试本地 JWT 解码并加载本地 User（统一账号系统）
    3. 失败则回退 Core Auth /auth/me（Strangler 双跑旧流量）
    """
    if not authorization or not authorization.startswith("Bearer "):
        msg = "缺少 Authorization 头或非 Bearer 类型"
        raise AuthError(msg)
    token = authorization.removeprefix("Bearer ").strip()

    local = await _try_local_principal(token, session)
    if local is not None:
        return local

    client = get_core_auth_client()
    try:
        return await client.me(token)
    except AppError as exc:
        if exc.http_status in (401, 403):
            raise AuthError("登录已失效，请重新登录") from exc
        raise AuthError("登录状态校验失败，请稍后重试") from exc


async def get_current_user_optional(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_db),
) -> CorePrincipal | None:
    """可选鉴权：有 token 则校验，无 token 返回 None。"""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    try:
        return await get_current_user(authorization, session)  # type: ignore[arg-type]
    except AuthError:
        return None


RoleLiteral = Literal["submitter", "reviewer", "supervisor", "admin", "librarian"]


def require_role(*allowed_roles: RoleLiteral):
    """角色守卫工厂：仅允许指定角色访问。

    用法：``current_user: User = Depends(require_role("admin"))``
    """
    allowed = {str(r) for r in allowed_roles}

    async def _guard(current_user: CorePrincipal = Depends(get_current_user)) -> CorePrincipal:
        if str(current_user.role) not in allowed:
            msg = f"权限不足：需要 {', '.join(allowed)} 角色，当前为 {current_user.role}"
            raise AuthError(msg)
        return current_user

    return _guard


# ============== M16.1 租户上下文 ==============


@dataclass(frozen=True)
class TenantContext:
    """当前请求的租户上下文。

    - user: 当前登录用户
    - org: 用户所属组织 (personal / 团队)
    - org_id: 便捷访问, 等于 user.organization_id
    - is_team: 是否为团队型组织 (律所/法务部)
    - is_super_admin: 是否超级管理员 (跨租户可见)
    """
    user: CorePrincipal
    org: Organization | None
    org_id: UUID | None
    is_team: bool
    is_super_admin: bool


async def get_tenant_context(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> TenantContext:
    """组合 user + org + 团队/超管标记。

    用法:
        ctx: TenantContext = Depends(get_tenant_context)
        stmt = apply_org_filter_with_column(
            stmt, ctx.user, ctx.org,
            org_column=ReviewTask.organization_id,
            user_id_column=ReviewTask.submitter_id,
        )
    """
    org = await load_user_org(session, current_user)
    super_admin = is_super_admin(current_user)
    is_team = (
        org is not None
        and str(org.type) != "personal"
        and not super_admin
    )
    return TenantContext(
        user=current_user,
        org=org,
        org_id=current_user.organization_id,
        is_team=is_team,
        is_super_admin=super_admin,
    )
