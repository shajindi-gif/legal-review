"""鉴权 API - 注册/登录/刷新/当前用户/登出。

所有路由前缀：/api/v1/auth
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    QuotaStatus,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserOut,
)
from app.services.audit import AuditService
from app.services.auth_service import AuthService
from app.services.quota_service import QuotaService

router = APIRouter(prefix="/auth", tags=["auth"])


def _user_to_out(user: User) -> dict:
    """将 User ORM 对象转为 UserOut dict（含 plan 字段）。"""
    plan = user.plan
    return {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "real_name": user.real_name,
        "company": user.company,
        "role": str(user.role),
        "plan_tier": str(plan.tier) if plan else "free",
        "quota_daily": plan.quota_daily if plan else 3,
        "used_today": plan.used_today if plan else 0,
        "last_login_at": user.last_login_at,
    }


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(
    body: RegisterRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> dict:
    """注册新用户 → 自动登录签发 Token。"""
    auth = AuthService(session)
    user = await auth.register(
        email=body.email,
        password=body.password,
        company=body.company,
        real_name=body.real_name,
    )
    # 审计
    audit = AuditService(session)
    await audit.log(
        action="create",
        actor_id=user.id,
        actor_role=str(user.role),
        target_type="user",
        target_id=user.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    tokens = auth.issue_tokens(user)
    await session.commit()
    return tokens


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> dict:
    """邮箱 + 密码登录。"""
    auth = AuthService(session)
    user = await auth.authenticate(email=body.email, password=body.password)
    audit = AuditService(session)
    await audit.log(
        action="create",
        actor_id=user.id,
        actor_role=str(user.role),
        target_type="session",
        target_id=user.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    tokens = auth.issue_tokens(user)
    await session.commit()
    return tokens


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    body: RefreshRequest,
    session: AsyncSession = Depends(get_db),
) -> dict:
    """用 refresh token 换取新的 access + refresh token。"""
    auth = AuthService(session)
    tokens = await auth.refresh_access(body.refresh_token)
    await session.commit()
    return tokens


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)) -> dict:
    """获取当前登录用户信息（含套餐配额）。"""
    # plan 通过 selectin 关系自动加载
    return _user_to_out(current_user)


@router.get("/quota", response_model=QuotaStatus)
async def get_quota(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """获取当前用户配额状态。"""
    quota = QuotaService(session)
    status = await quota.get_status(current_user.id)
    await session.commit()
    return status


@router.post("/logout")
async def logout(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """登出（JWT 无状态，客户端清除 Token 即可）。

    服务端仅记录审计日志，不做 token 黑名单（如需可后续接入 Redis）。
    """
    audit = AuditService(session)
    await audit.log(
        action="delete",
        actor_id=current_user.id,
        actor_role=str(current_user.role),
        target_type="session",
        target_id=current_user.id,
    )
    await session.commit()
    return {"message": "已登出"}
