"""账号与安全中心。

路由前缀：/api/v1/account（均需登录）
- GET  /account/identities            查看已绑定登录方式（脱敏）
- POST /account/bind                  绑定手机号 / 邮箱（验证码）
- POST /account/unbind                解绑手机号 / 邮箱（保护最后一种登录方式）
- GET  /account/sessions              我的活跃会话
- POST /account/sessions/logout-all   退出其他所有会话
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.models.identity import OAuthIdentity
from app.models.user import User
from app.schemas.auth import SessionListResponse, SessionOut
from app.services.auth_service import AuthService
from app.services.core_auth_client import CorePrincipal
from app.services.verification import VerificationService
from app.utils.phone import mask_email, mask_phone, normalize_email, normalize_phone

router = APIRouter(prefix="/account", tags=["account"])

_CORE_BRIDGE_HASH = "!core-bridge!"


# ============== Schemas ==============


class LinkedIdentityOut(BaseModel):
    channel: str
    bound: bool
    masked_target: str | None = None
    verified: bool = False


class IdentitiesResponse(BaseModel):
    identities: list[LinkedIdentityOut]


class BindIdentityRequest(BaseModel):
    channel: Literal["phone", "email"]
    target: str = Field(min_length=3, max_length=255)
    code: str = Field(min_length=4, max_length=8)


class BindIdentityResponse(BaseModel):
    success: bool = True
    masked_target: str


class UnbindIdentityRequest(BaseModel):
    channel: Literal["phone", "email"]


class UnbindIdentityResponse(BaseModel):
    success: bool = True


# ============== 内部 helper ==============


async def _load_local_user(
    session: AsyncSession, principal: CorePrincipal
) -> User:
    """加载本地 User；账号安全中心只作用于本地统一账号。"""
    user = await session.get(User, principal.id)
    if user is None:
        raise NotFoundError("本地账号不存在，账号中心仅对统一账号开放")
    return user


async def _count_login_methods(session: AsyncSession, user: User) -> int:
    """统计当前账号可用的登录方式数量（邮箱 / 手机 / 密码 / OAuth）。"""
    n = 0
    if user.email:
        n += 1
    if user.phone:
        n += 1
    if user.password_hash and user.password_hash not in ("", _CORE_BRIDGE_HASH):
        n += 1
    oauth = await session.scalar(
        select(func.count(OAuthIdentity.id)).where(OAuthIdentity.user_id == user.id)
    )
    n += int(oauth or 0)
    return n


def _purpose_for(channel: str) -> str:
    return "bind_phone" if channel == "phone" else "bind_email"


# ============== 端点 ==============


@router.get("/identities", response_model=IdentitiesResponse)
async def list_identities(
    current_user: CorePrincipal = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> IdentitiesResponse:
    """查看已绑定登录方式（敏感信息脱敏）。"""
    user = await _load_local_user(session, current_user)

    oauth_rows = (
        await session.execute(
            select(OAuthIdentity).where(OAuthIdentity.user_id == user.id)
        )
    ).scalars().all()
    oauth_by_provider = {r.provider: r for r in oauth_rows}

    has_password = bool(
        user.password_hash and user.password_hash not in ("", _CORE_BRIDGE_HASH)
    )

    identities = [
        LinkedIdentityOut(
            channel="phone",
            bound=bool(user.phone),
            masked_target=mask_phone(user.phone) if user.phone else None,
            verified=user.phone_verified_at is not None,
        ),
        LinkedIdentityOut(
            channel="email",
            bound=bool(user.email),
            masked_target=mask_email(user.email) if user.email else None,
            verified=user.email_verified_at is not None,
        ),
        LinkedIdentityOut(channel="password", bound=has_password),
    ]
    for provider, label in (
        ("wechat", "微信"),
        ("qq", "QQ"),
        ("weibo", "微博"),
    ):
        row = oauth_by_provider.get(provider)
        identities.append(
            LinkedIdentityOut(
                channel=provider,
                bound=row is not None,
                masked_target=row.provider_display_name if row else None,
                verified=bool(row.provider_email_verified) if row else False,
            )
        )

    return IdentitiesResponse(identities=identities)


@router.post("/bind", response_model=BindIdentityResponse)
async def bind_identity(
    body: BindIdentityRequest,
    current_user: CorePrincipal = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> BindIdentityResponse:
    """绑定手机号 / 邮箱：验证码校验 + 冲突检测（新身份属于他人则不覆盖）。"""
    target = (
        normalize_phone(body.target)
        if body.channel == "phone"
        else normalize_email(body.target)
    )

    svc = VerificationService(session)
    await svc.verify(target=target, code=body.code, purpose=_purpose_for(body.channel))

    user = await _load_local_user(session, current_user)

    # 冲突检测：身份已属于其他账号 → 明确提示，不覆盖原绑定
    if body.channel == "phone":
        existing = await session.scalar(select(User).where(User.phone == target))
        other = existing is not None and existing.id != user.id
    else:
        existing = await session.scalar(select(User).where(User.email == target))
        other = existing is not None and existing.id != user.id

    if other:
        raise ConflictError("该联系方式已绑定其他账号，请先解绑原账号")

    now = datetime.now(UTC)
    if body.channel == "phone":
        user.phone = target
        user.phone_verified_at = now
        masked = mask_phone(target)
    else:
        user.email = target
        user.email_verified_at = now
        masked = mask_email(target)

    try:
        await session.flush()
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError("该联系方式已绑定其他账号") from exc
    return BindIdentityResponse(success=True, masked_target=masked)


@router.post("/unbind", response_model=UnbindIdentityResponse)
async def unbind_identity(
    body: UnbindIdentityRequest,
    current_user: CorePrincipal = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> UnbindIdentityResponse:
    """解绑手机号 / 邮箱：禁止解绑最后一种登录方式。"""
    user = await _load_local_user(session, current_user)

    if body.channel == "phone":
        if not user.phone:
            raise NotFoundError("未绑定手机号")
        target_is_current = True
    elif body.channel == "email":
        if not user.email:
            raise NotFoundError("未绑定邮箱")
        target_is_current = True
    else:
        raise ValidationError("不支持的绑定类型")

    if not target_is_current:
        raise ValidationError("当前身份不存在")

    if await _count_login_methods(session, user) <= 1:
        raise ConflictError("不能解绑最后一种登录方式，请先添加其他登录方式")

    if body.channel == "phone":
        user.phone = None
        user.phone_verified_at = None
    else:
        user.email = None
        user.email_verified_at = None

    await session.flush()
    await session.commit()
    return UnbindIdentityResponse(success=True)


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions(
    current_user: CorePrincipal = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> SessionListResponse:
    """列出当前账号的活跃会话。"""
    user = await _load_local_user(session, current_user)
    auth = AuthService(session)
    rows = await auth.list_sessions(user.id)
    return SessionListResponse(
        sessions=[SessionOut(**r) for r in rows]
    )


@router.post("/sessions/logout-all")
async def logout_all_sessions(
    current_user: CorePrincipal = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """退出所有其他会话（撤销全部 refresh token）。"""
    user = await _load_local_user(session, current_user)
    auth = AuthService(session)
    revoked = await auth.revoke_all_user_tokens(user.id)
    await session.commit()
    return {"success": True, "revoked": revoked}