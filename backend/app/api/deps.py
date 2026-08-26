"""FastAPI 依赖注入 - DB session / Sandbox / 审计 / 鉴权 / 租户上下文。"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AuthError
from app.db.session import get_db as _get_db
from app.models.user import Organization, User
from app.services.audit import AuditService
from app.services.auth_service import decode_token
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


async def get_current_user(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_db),
) -> User:
    """从 Authorization: Bearer <token> 解析当前用户。

    流程：
    1. 提取 Bearer token
    2. JWT 解码 → user_id
    3. 查 DB → User 对象（含 plan 关系）
    4. 校验账号状态 active
    """
    if not authorization or not authorization.startswith("Bearer "):
        msg = "缺少 Authorization 头或非 Bearer 类型"
        raise AuthError(msg)
    token = authorization.removeprefix("Bearer ").strip()
    payload = decode_token(token)
    if payload.get("type") != "access":
        msg = "需要 access token，而非 refresh token"
        raise AuthError(msg)
    user_id_str = payload.get("sub")
    if not user_id_str:
        msg = "Token payload 缺少 sub"
        raise AuthError(msg)
    user = await session.get(User, UUID(user_id_str))
    if user is None:
        msg = "用户不存在或已删除"
        raise AuthError(msg)
    if str(user.status) != "active":
        msg = f"账号状态异常: {user.status}"
        raise AuthError(msg)
    return user


async def get_current_user_optional(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_db),
) -> User | None:
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

    async def _guard(current_user: User = Depends(get_current_user)) -> User:
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
    user: User
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
