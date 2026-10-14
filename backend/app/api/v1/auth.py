"""鉴权 API —— 本地统一账号（M0 身份系统）+ Core Strangler 双跑。

路由前缀：/api/v1/auth
- POST /register、POST /login、GET /me：仍走 Core（邮箱密码老流程，双跑期保留）
- 统一账号（本地 M0 身份系统）：
  - POST /sms/send            手机验证码发送
  - POST /email/send          邮箱验证码发送
  - POST /login/verification  验证码统一登录/注册（phone/email）
  - POST /login/phone         手机号 + 密码（兼容入口，本地）
  - POST /refresh             本地持久化 refresh token 轮换
  - POST /logout              撤销当前会话 refresh token
  - GET  /login-methods       登录方式开关
- GET /quota：packages/quota 未接入前保留冻结 501（不影响登录主链路）
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.config import get_settings
from app.core.constants import FREE_TRIAL_LIMIT, PlanTier
from app.core.errors import AppError
from app.schemas.auth import (
    EmailSendRequest,
    EmailSendResponse,
    LoginMethod,
    LoginMethodsResponse,
    LoginRequest,
    LogoutRequest,
    PhoneLoginRequest,
    QuotaStatus,
    RefreshRequest,
    RegisterRequest,
    SmsSendRequest,
    SmsSendResponse,
    TokenResponse,
    UserOut,
    VerificationLoginRequest,
    VerificationLoginResponse,
)
from app.services.auth_service import AuthService
from app.services.core_auth_client import CorePrincipal, get_core_auth_client
from app.services.verification import VerificationService
from app.utils.phone import normalize_email, normalize_phone

router = APIRouter(prefix="/auth", tags=["auth"])

_QUOTA_FROZEN_MSG = "配额状态端点等待 packages/quota 接入，暂未开放"


def _quota_frozen() -> AppError:
    return AppError(code="not_implemented", message=_QUOTA_FROZEN_MSG, http_status=501)


# ============== Core Auth（双跑期保留的旧流程） ==============


def _tokens_payload(data: dict) -> dict:
    """Core 登录/预置响应 → legal-review TokenResponse 兼容 dict。"""
    return {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token", ""),
        "token_type": data.get("token_type", "bearer"),
        "expires_in": data.get("expires_in", 0),
    }


def _principal_to_out(p: CorePrincipal) -> dict:
    """CorePrincipal → legal-review UserOut 兼容 dict。"""
    return {
        "id": p.id,
        "email": p.email,
        "username": p.username,
        "real_name": p.real_name,
        "company": p.company,
        "role": str(p.role),
        "plan_tier": "free",
        "quota_daily": FREE_TRIAL_LIMIT,
        "used_today": 0,
        "remaining": FREE_TRIAL_LIMIT,
        "last_login_at": p.last_login_at,
        "tenant_id": p.tenant_id,
    }


def _derive_tenant_slug(email: str) -> str:
    """从邮箱 local-part 派生合法 tenant_slug。"""
    local = email.split("@")[0].lower()
    slug = "".join(ch if ch.isalnum() else "-" for ch in local).strip("-")
    slug = slug[:48] or "legal"
    return slug


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(body: RegisterRequest) -> TokenResponse:
    """邮箱注册 → Core provision-tenant，路径等价旧 register。"""
    client = get_core_auth_client()
    name = body.real_name or body.email.split("@")[0]
    tenant_name = body.company or f"{name} 工作台"
    data = await client.provision_tenant(
        tenant_name=tenant_name,
        tenant_slug=_derive_tenant_slug(body.email),
        owner_email=body.email,
        owner_name=name,
        owner_password=body.password,
    )
    return TokenResponse(**_tokens_payload(data))


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest) -> TokenResponse:
    """邮箱密码登录 → Core /auth/login。"""
    client = get_core_auth_client()
    data = await client.login(email=body.email, password=body.password)
    return TokenResponse(**_tokens_payload(data))


@router.get("/me", response_model=UserOut)
async def me(current_user: CorePrincipal = Depends(get_current_user)) -> UserOut:
    """当前用户（本地 JWT 或 Core /auth/me 双兼容）。"""
    return UserOut(**_principal_to_out(current_user))


# ============== 统一账号（本地 M0 身份系统） ==============


def _client_ip(request: Request) -> str | None:
    """取直连客户端 IP。可信代理下的 X-Forwarded-For 解析见生产运维配置。"""
    return request.client.host if request.client else None


def _client_ua(request: Request) -> str | None:
    return request.headers.get("user-agent")


def _local_user_out(user) -> dict:
    """本地 User ORM → UserOut 兼容 dict。"""
    tier = PlanTier.FREE
    quota_daily = FREE_TRIAL_LIMIT
    used_today = 0
    remaining = FREE_TRIAL_LIMIT
    if user.plan is not None:
        tier = user.plan.tier
        if str(tier) in (PlanTier.PRO.value, PlanTier.ENTERPRISE.value):
            quota_daily = -1
            remaining = -1
            used_today = 0
        else:
            limit = user.plan.free_trial_limit or FREE_TRIAL_LIMIT
            used = user.plan.free_trial_used or 0
            quota_daily = limit
            used_today = used
            remaining = max(0, limit - used)
    return {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "real_name": user.real_name,
        "company": user.company,
        "role": str(user.role),
        "plan_tier": str(tier),
        "quota_daily": quota_daily,
        "used_today": used_today,
        "remaining": remaining,
        "last_login_at": user.last_login_at,
        "tenant_id": None,
    }


def _require_channel(enabled: bool, label: str) -> None:
    if not enabled:
        raise AppError(code="channel_disabled", message=f"{label}登录未开通", http_status=403)


@router.post("/sms/send", response_model=SmsSendResponse)
async def sms_send(
    body: SmsSendRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> SmsSendResponse:
    """发送手机验证码（本地）。未配置真实短信渠道时 auth_sms_enabled=False 直接 403。"""
    _require_channel(get_settings().auth_sms_enabled, "短信")
    phone = normalize_phone(body.phone)
    svc = VerificationService(session)
    result = await svc.send_code(
        target=phone,
        channel="sms",
        purpose=body.purpose,
        ip_address=_client_ip(request),
        user_agent=_client_ua(request),
    )
    await session.commit()
    return SmsSendResponse(success=True, expires_in=result.expires_in, mock_code=result.mock_code)


@router.post("/email/send", response_model=EmailSendResponse)
async def email_send(
    body: EmailSendRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> EmailSendResponse:
    """发送邮箱验证码（本地）。未配置真实邮件渠道时 auth_email_enabled=False 直接 403。"""
    _require_channel(get_settings().auth_email_enabled, "邮箱")
    email = normalize_email(body.email)
    svc = VerificationService(session)
    result = await svc.send_code(
        target=email,
        channel="email",
        purpose=body.purpose,
        ip_address=_client_ip(request),
        user_agent=_client_ua(request),
    )
    await session.commit()
    return EmailSendResponse(success=True, expires_in=result.expires_in, mock_code=result.mock_code)


@router.post("/login/verification", response_model=VerificationLoginResponse)
async def login_verification(
    body: VerificationLoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> VerificationLoginResponse:
    """验证码统一登录/注册：已有身份登录原账号，新身份创建账号。"""
    settings = get_settings()
    if body.channel == "phone":
        _require_channel(settings.auth_sms_enabled, "短信")
        target = normalize_phone(body.target)
    else:
        _require_channel(settings.auth_email_enabled, "邮箱")
        target = normalize_email(body.target)

    svc = VerificationService(session)
    await svc.verify(target=target, code=body.code, purpose="login")

    auth = AuthService(session)
    user, is_new = await auth.login_or_register_by_identity(
        channel=body.channel, target=target
    )
    pair = await auth.issue_token_pair(
        user,
        ip_address=_client_ip(request),
        user_agent=_client_ua(request),
    )
    await session.refresh(user, attribute_names=["plan"])
    out = UserOut(**_local_user_out(user))
    await session.commit()
    return VerificationLoginResponse(**pair, is_new_user=is_new, user=out)


@router.post("/login/phone", response_model=VerificationLoginResponse)
async def login_phone(
    body: PhoneLoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> VerificationLoginResponse:
    """手机号 + 密码登录（兼容入口，本地）。"""
    phone = normalize_phone(body.phone)
    auth = AuthService(session)
    user = await auth.authenticate_by_phone(phone=phone, password=body.password)
    pair = await auth.issue_token_pair(
        user,
        ip_address=_client_ip(request),
        user_agent=_client_ua(request),
    )
    await session.refresh(user, attribute_names=["plan"])
    out = UserOut(**_local_user_out(user))
    await session.commit()
    return VerificationLoginResponse(**pair, is_new_user=False, user=out)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    body: RefreshRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """刷新 token（本地持久化轮换：旧 refresh 作废，签发新对）。"""
    auth = AuthService(session)
    pair = await auth.refresh_token_pair(
        body.refresh_token,
        ip_address=_client_ip(request),
        user_agent=_client_ua(request),
    )
    await session.commit()
    return TokenResponse(**pair)


@router.post("/logout")
async def logout(
    body: LogoutRequest,
    session: AsyncSession = Depends(get_db),
) -> dict:
    """登出：撤销当前会话的 refresh token（幂等）。"""
    auth = AuthService(session)
    if body.refresh_token:
        await auth.revoke_refresh_token(body.refresh_token)
    await session.commit()
    return {"success": True}


@router.get("/login-methods", response_model=LoginMethodsResponse)
async def login_methods() -> LoginMethodsResponse:
    """登录方式开关（未开通渠道 enabled=False，前台不展示）。"""
    s = get_settings()
    return LoginMethodsResponse(
        methods=[
            LoginMethod(key="phone", enabled=s.auth_sms_enabled, label="手机号验证码"),
            LoginMethod(key="email", enabled=s.auth_email_enabled, label="邮箱验证码"),
            LoginMethod(key="password", enabled=s.auth_password_enabled, label="账号密码"),
            LoginMethod(key="wechat", enabled=s.auth_wechat_enabled, label="微信"),
            LoginMethod(key="qq", enabled=s.auth_qq_enabled, label="QQ"),
            LoginMethod(key="weibo", enabled=s.auth_weibo_enabled, label="微博"),
            LoginMethod(key="xiaohongshu", enabled=s.auth_xiaohongshu_enabled, label="小红书"),
        ]
    )


# ============== 冻结端点（packages/quota 未接入） ==============


@router.get("/quota", response_model=QuotaStatus)
async def quota() -> QuotaStatus:
    """配额状态：packages/quota 后续接入，冻结（无需鉴权）。"""
    raise _quota_frozen()