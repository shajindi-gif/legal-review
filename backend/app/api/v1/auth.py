"""鉴权 API —— 本地统一账号（M0 身份系统）+ Core Strangler 双跑。

路由前缀：/api/v1/auth
- POST /register、POST /login、GET /me：仍走 Core（邮箱密码老流程，双跑期保留）
- 统一账号（本地 M0 身份系统）：
  - POST /register/password   本地邮箱密码注册（agreed_terms 合规）
  - POST /login/password      统一身份密码登录（本地优先，Core 回退兜底老用户）
  - POST /sms/send            手机验证码发送
  - POST /email/send          邮箱验证码发送
  - POST /login/verification  验证码统一登录/注册（phone/email）
  - POST /login/phone         手机号 + 密码（兼容入口，本地）
  - POST /password/forgot     忘记密码（邮箱验证码，防枚举恒 200）
  - POST /password/reset      重置密码（验证码 + 新密码，撤销全部会话）
  - POST /password/change     修改密码（需登录，保留当前会话）
  - POST /account/bind        绑定/换绑手机号或邮箱（需登录，验证码）
  - GET  /account             用户中心资料（含验证状态）
  - PATCH /account            更新基本资料（real_name / company）
  - GET  /sessions            活跃会话列表（设备管理）
  - DELETE /sessions/{id}     撤销指定会话
  - POST /logout-all          退出所有设备
  - POST /refresh             本地持久化 refresh token 轮换（优先 HttpOnly Cookie）
  - POST /logout              撤销当前会话 refresh token（Cookie 优先）
  - GET  /login-methods       登录方式开关
- GET /quota：packages/quota 未接入前保留冻结 501（不影响登录主链路）

安全设计：
- refresh token 通过 HttpOnly Cookie（lr_rt, Path=/api/v1/auth, SameSite=Lax）下发，
  前端 JS 不再持有 30 天凭证（XSS 缓解）；body 传 token 的旧模式保留兼容。
- 全部登录端点写 user_login_events 审计（成功 + 失败）。
- 忘记密码防枚举：无论邮箱是否存在恒返回成功。
"""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.config import get_settings
from app.core.constants import FREE_TRIAL_LIMIT, PlanTier
from app.core.errors import AppError, AuthError, NotFoundError, RateLimitedError
from app.models.identity import UserLoginEvent
from app.models.user import User
from app.schemas.auth import (
    AccountProfileResponse,
    BindAccountRequest,
    BindAccountResponse,
    ChangePasswordRequest,
    EmailSendRequest,
    EmailSendResponse,
    ForgotPasswordRequest,
    LoginMethod,
    LoginMethodsResponse,
    LoginRequest,
    LogoutRequest,
    PasswordLoginRequest,
    PasswordRegisterRequest,
    PhoneLoginRequest,
    QuotaStatus,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    SessionListResponse,
    SmsSendRequest,
    SmsSendResponse,
    TokenResponse,
    UpdateProfileRequest,
    UserOut,
    VerificationLoginRequest,
    VerificationLoginResponse,
)
from app.services.auth_service import AuthService
from app.services.core_auth_client import CorePrincipal, get_core_auth_client
from app.services.verification import VerificationService
from app.utils.phone import mask_email, mask_phone, normalize_email, normalize_phone

router = APIRouter(prefix="/auth", tags=["auth"])

_QUOTA_FROZEN_MSG = "配额状态端点等待 packages/quota 接入，暂未开放"

# HttpOnly refresh cookie 名与作用域（仅 /api/v1/auth* 携带，降低暴露面）
REFRESH_COOKIE = "lr_rt"
REFRESH_COOKIE_PATH = "/api/v1/auth"


def _quota_frozen() -> AppError:
    return AppError(code="not_implemented", message=_QUOTA_FROZEN_MSG, http_status=501)


# ============== Cookie / 审计辅助 ==============


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    """下发 HttpOnly refresh cookie。生产强制 Secure。"""
    settings = get_settings()
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=refresh_token,
        max_age=settings.refresh_token_ttl_days * 86400,
        httponly=True,
        secure=settings.environment.lower() in ("production", "prod"),
        samesite="lax",
        path=REFRESH_COOKIE_PATH,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(key=REFRESH_COOKIE, path=REFRESH_COOKIE_PATH)


def _refresh_from_request(request: Request, body_token: str | None) -> str | None:
    """refresh token 读取顺序：HttpOnly Cookie 优先，其次 body（旧客户端兼容）。"""
    return request.cookies.get(REFRESH_COOKIE) or body_token or None


def _log_login_event(
    session: AsyncSession,
    *,
    user_id=None,
    identifier: str | None,
    method: str,
    success: bool,
    failure_reason: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    """写登录审计事件。审计写入失败不影响主流程。"""
    import structlog

    try:
        session.add(
            UserLoginEvent(
                user_id=user_id,
                identifier=(identifier[:128] if identifier else None),
                login_method=method[:32],
                success=success,
                failure_reason=(failure_reason[:64] if failure_reason else None),
                ip_address=ip_address,
                user_agent=(user_agent[:512] if user_agent else None),
            )
        )
    except Exception:  # noqa: BLE001 - 审计失败不阻断登录
        structlog.get_logger("auth.audit").warning(
            "login_event_write_failed", method=method, success=success
        )


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


def _local_user_out(user: User) -> dict:
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


# ============== 本地密码注册 / 统一密码登录（P0 新增） ==============


@router.post("/register/password", response_model=VerificationLoginResponse, status_code=201)
async def register_password(
    body: PasswordRegisterRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db),
) -> VerificationLoginResponse:
    """本地邮箱密码注册：创建用户 + Free 套餐，直接登录并下发会话。

    - 与验证码注册共用 login_or_register_by_identity 的资产初始化逻辑
    - agreed_terms 落库 agreed_terms_at（个保法合规）
    """
    _require_channel(get_settings().auth_password_enabled, "密码注册")
    if not body.agreed_terms:
        raise AppError(code="terms_required", message="请先阅读并同意服务条款与隐私政策", http_status=400)

    email = normalize_email(body.email)
    auth = AuthService(session)
    existing = await auth.find_by_email(email)
    if existing is not None:
        raise AppError(code="conflict", message="该邮箱已注册，请直接登录", http_status=409)

    # 复用 register：个人组织 + Free 套餐 + Argon2id
    user = await auth.register(
        email=email,
        password=body.password,
        company=body.company,
        real_name=body.real_name,
    )
    user.agreed_terms_at = datetime.now(UTC).replace(tzinfo=None)
    pair = await auth.issue_token_pair(
        user,
        ip_address=_client_ip(request),
        user_agent=_client_ua(request),
    )
    _log_login_event(
        session,
        user_id=user.id,
        identifier=mask_email(email),
        method="register_password",
        success=True,
        ip_address=_client_ip(request),
        user_agent=_client_ua(request),
    )
    await session.refresh(user, attribute_names=["plan"])
    out = UserOut(**_local_user_out(user))
    await session.commit()
    _set_refresh_cookie(response, pair["refresh_token"])
    return VerificationLoginResponse(**pair, is_new_user=True, user=out)


@router.post("/login/password", response_model=VerificationLoginResponse)
async def login_password(
    body: PasswordLoginRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db),
) -> VerificationLoginResponse:
    """统一身份密码登录：本地账号优先，失败回退 Core（兼容双跑期老用户）。

    - identifier 自动识别邮箱 / 手机号
    - 所有结果（本地成败 + Core 成败）均写 user_login_events
    - 防枚举：本地失败与 Core 失败统一「账号或密码错误」
    """
    ident = body.identifier.strip()
    auth = AuthService(session)

    try:
        user = await auth.authenticate_by_identifier(identifier=ident, password=body.password)
        pair = await auth.issue_token_pair(
            user,
            ip_address=_client_ip(request),
            user_agent=_client_ua(request),
        )
        masked = mask_email(ident) if "@" in ident else mask_phone(ident)
        _log_login_event(
            session,
            user_id=user.id,
            identifier=masked,
            method="password",
            success=True,
            ip_address=_client_ip(request),
            user_agent=_client_ua(request),
        )
        await session.refresh(user, attribute_names=["plan"])
        out = UserOut(**_local_user_out(user))
        await session.commit()
        _set_refresh_cookie(response, pair["refresh_token"])
        return VerificationLoginResponse(**pair, is_new_user=False, user=out)
    except AuthError:
        await session.rollback()

    # 本地失败 → Core 回退（老用户凭证在 Core 侧；Core 仅支持邮箱）
    if "@" not in ident:
        _log_login_event(
            session,
            identifier=mask_phone(ident),
            method="password",
            success=False,
            failure_reason="bad_credentials",
            ip_address=_client_ip(request),
            user_agent=_client_ua(request),
        )
        await session.commit()
        raise AuthError("账号或密码错误")

    client = get_core_auth_client()
    try:
        data = await client.login(email=ident, password=body.password)
    except AppError:
        _log_login_event(
            session,
            identifier=mask_email(ident),
            method="password",
            success=False,
            failure_reason="bad_credentials",
            ip_address=_client_ip(request),
            user_agent=_client_ua(request),
        )
        await session.commit()
        raise AuthError("账号或密码错误") from None

    _log_login_event(
        session,
        identifier=mask_email(ident),
        method="password_core",
        success=True,
        ip_address=_client_ip(request),
        user_agent=_client_ua(request),
    )
    await session.commit()
    # Core 登录成功 → 用 Core access token 换取真实 principal（前端也可后续 GET /auth/me）
    try:
        principal = await client.me(data["access_token"])
    except AppError:
        principal = None
    if principal is not None:
        user_out = UserOut(**_principal_to_out(principal))
    else:
        user_out = UserOut(
            id=uuid4(), email=ident, username=ident.split("@")[0], real_name="",
            role="submitter",
        )
    return VerificationLoginResponse(**_tokens_payload(data), is_new_user=False, user=user_out)


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
    response: Response,
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
    _log_login_event(
        session,
        user_id=user.id,
        identifier=mask_phone(target) if body.channel == "phone" else mask_email(target),
        method=f"verification_{body.channel}",
        success=True,
        ip_address=_client_ip(request),
        user_agent=_client_ua(request),
    )
    await session.refresh(user, attribute_names=["plan"])
    out = UserOut(**_local_user_out(user))
    await session.commit()
    _set_refresh_cookie(response, pair["refresh_token"])
    return VerificationLoginResponse(**pair, is_new_user=is_new, user=out)


@router.post("/login/phone", response_model=VerificationLoginResponse)
async def login_phone(
    body: PhoneLoginRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db),
) -> VerificationLoginResponse:
    """手机号 + 密码登录（兼容入口，本地）。"""
    phone = normalize_phone(body.phone)
    auth = AuthService(session)
    try:
        user = await auth.authenticate_by_phone(phone=phone, password=body.password)
    except AuthError:
        _log_login_event(
            session,
            identifier=mask_phone(phone),
            method="phone_password",
            success=False,
            failure_reason="bad_credentials",
            ip_address=_client_ip(request),
            user_agent=_client_ua(request),
        )
        await session.commit()
        raise
    pair = await auth.issue_token_pair(
        user,
        ip_address=_client_ip(request),
        user_agent=_client_ua(request),
    )
    _log_login_event(
        session,
        user_id=user.id,
        identifier=mask_phone(phone),
        method="phone_password",
        success=True,
        ip_address=_client_ip(request),
        user_agent=_client_ua(request),
    )
    await session.refresh(user, attribute_names=["plan"])
    out = UserOut(**_local_user_out(user))
    await session.commit()
    _set_refresh_cookie(response, pair["refresh_token"])
    return VerificationLoginResponse(**pair, is_new_user=False, user=out)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    body: RefreshRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """刷新 token（本地持久化轮换：旧 refresh 作废，签发新对）。

    token 来源优先 HttpOnly Cookie（lr_rt）；body 传 token 的旧模式保留兼容。
    Cookie 模式下响应体不回传 refresh_token（避免 JS 读取），改写 Set-Cookie。
    """
    auth = AuthService(session)
    raw_token = _refresh_from_request(request, body.refresh_token)
    if not raw_token:
        raise AuthError("缺少 refresh token")
    pair = await auth.refresh_token_pair(
        raw_token,
        ip_address=_client_ip(request),
        user_agent=_client_ua(request),
    )
    await session.commit()
    from_cookie = request.cookies.get(REFRESH_COOKIE) is not None
    if from_cookie:
        _set_refresh_cookie(response, pair["refresh_token"])
        return TokenResponse(
            access_token=pair["access_token"],
            refresh_token="",
            token_type=pair["token_type"],
            expires_in=pair["expires_in"],
        )
    return TokenResponse(**pair)


@router.post("/logout")
async def logout(
    body: LogoutRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db),
) -> dict:
    """登出：撤销当前会话的 refresh token（幂等；Cookie 或 body 任一）。"""
    auth = AuthService(session)
    raw_token = _refresh_from_request(request, body.refresh_token)
    if raw_token:
        await auth.revoke_refresh_token(raw_token)
    await session.commit()
    _clear_refresh_cookie(response)
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


# ============== 密码管理（P0 新增） ==============


@router.post("/password/forgot")
async def password_forgot(
    body: ForgotPasswordRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> dict:
    """忘记密码：向邮箱发送 reset_password 验证码。

    防枚举：无论邮箱是否存在，恒返回 success=true。
    邮件渠道未开通时返回 503（全局状态，不泄露单账户信息）。
    """
    settings = get_settings()
    _require_channel(settings.auth_email_enabled, "邮箱")

    email = normalize_email(body.email)
    auth = AuthService(session)
    user = await auth.find_by_email(email)
    if user is None or not user.password_hash:
        # 不存在 / 验证码注册无密码账户 → 静默成功，不发邮件
        return {"success": True, "message": "如果该邮箱已注册，重置邮件已发送"}

    svc = VerificationService(session)
    try:
        await svc.send_code(
            target=email,
            channel="email",
            purpose="reset_password",
            ip_address=_client_ip(request),
            user_agent=_client_ua(request),
        )
    except RateLimitedError:
        # 频控错误照常返回（429 由全局异常处理器输出），避免被用于绕过限流探测
        raise
    except AppError:
        return {"success": True, "message": "如果该邮箱已注册，重置邮件已发送"}
    await session.commit()
    return {"success": True, "message": "如果该邮箱已注册，重置邮件已发送"}


@router.post("/password/reset")
async def password_reset(
    body: ResetPasswordRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> dict:
    """重置密码：邮箱验证码校验通过后设置新密码，并撤销该用户全部会话。"""
    email = normalize_email(body.email)
    svc = VerificationService(session)
    await svc.verify(target=email, code=body.code, purpose="reset_password")

    auth = AuthService(session)
    user = await auth.find_by_email(email)
    if user is None:
        # 验证码已消耗但账户不存在：极小概率（发送时校验过）——不泄露，统一报错
        raise AuthError("重置链接已失效，请重新操作")
    await auth.set_password(user, body.new_password)
    await auth.revoke_all_user_tokens(user.id)
    await session.commit()
    return {"success": True, "message": "密码已重置，请使用新密码登录"}


@router.post("/password/change")
async def password_change(
    body: ChangePasswordRequest,
    request: Request,
    response: Response,
    current_user: CorePrincipal = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """修改密码（需登录）：验证当前密码 → 新密码落库，撤销其他设备会话（保留当前）。"""
    auth = AuthService(session)
    user = await auth.get_user_by_id(current_user.id)
    await auth.change_password(user, body.current_password, body.new_password)

    # 撤销其他会话，保留当前设备（当前 refresh token 从 cookie 读取）
    keep_raw = request.cookies.get(REFRESH_COOKIE)
    revoked = await auth.revoke_other_user_tokens(user.id, keep_raw) if keep_raw else (
        await auth.revoke_all_user_tokens(user.id)
    )
    await session.commit()
    return {"success": True, "revoked_other_sessions": revoked}


# ============== 账户资料与绑定（P0 新增） ==============


@router.get("/account", response_model=AccountProfileResponse)
async def account_profile(
    current_user: CorePrincipal = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> AccountProfileResponse:
    """用户中心资料：凭证 + 验证状态 + 套餐 + 偏好。"""
    auth = AuthService(session)
    user = await auth.get_user_by_id(current_user.id)
    return AccountProfileResponse(
        id=user.id,
        username=user.username,
        real_name=user.real_name,
        email=user.email,
        email_verified=user.email_verified_at is not None,
        phone=user.phone,
        phone_verified=user.phone_verified_at is not None,
        company=user.company,
        role=str(user.role),
        plan_tier=str(user.plan.tier) if user.plan is not None else PlanTier.FREE,
        locale=user.locale,
        timezone=user.timezone,
        created_at=getattr(user, "created_at", None),
        last_login_at=user.last_login_at,
        has_password=bool(user.password_hash),
    )


@router.patch("/account", response_model=AccountProfileResponse)
async def account_update(
    body: UpdateProfileRequest,
    current_user: CorePrincipal = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> AccountProfileResponse:
    """更新基本资料（real_name / company）。不涉及凭证，无需再验证。"""
    auth = AuthService(session)
    user = await auth.get_user_by_id(current_user.id)
    if body.real_name is not None:
        user.real_name = body.real_name.strip()
    if body.company is not None:
        user.company = body.company.strip() or None
    await session.commit()
    await session.refresh(user, attribute_names=["plan"])
    return AccountProfileResponse(
        id=user.id,
        username=user.username,
        real_name=user.real_name,
        email=user.email,
        email_verified=user.email_verified_at is not None,
        phone=user.phone,
        phone_verified=user.phone_verified_at is not None,
        company=user.company,
        role=str(user.role),
        plan_tier=str(user.plan.tier) if user.plan is not None else PlanTier.FREE,
        locale=user.locale,
        timezone=user.timezone,
        created_at=getattr(user, "created_at", None),
        last_login_at=user.last_login_at,
        has_password=bool(user.password_hash),
    )


@router.post("/account/bind", response_model=BindAccountResponse)
async def account_bind(
    body: BindAccountRequest,
    request: Request,
    current_user: CorePrincipal = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> BindAccountResponse:
    """绑定/换绑手机号或邮箱（需登录）：验证码校验通过后写入。"""
    settings = get_settings()
    if body.channel == "phone":
        _require_channel(settings.auth_sms_enabled, "短信")
        target = normalize_phone(body.target)
        if body.purpose not in ("bind_phone", "change_phone"):
            raise AppError(code="validation_error", message="purpose 与渠道不匹配", http_status=422)
    else:
        _require_channel(settings.auth_email_enabled, "邮箱")
        target = normalize_email(body.target)
        if body.purpose not in ("bind_email", "change_email"):
            raise AppError(code="validation_error", message="purpose 与渠道不匹配", http_status=422)

    svc = VerificationService(session)
    await svc.verify(target=target, code=body.code, purpose=body.purpose)

    auth = AuthService(session)
    user = await auth.get_user_by_id(current_user.id)
    final = await auth.bind_identity(user, channel=body.channel, target=target)
    await session.commit()
    return BindAccountResponse(
        success=True,
        channel=body.channel,
        target=mask_phone(final) if body.channel == "phone" else mask_email(final),
    )


# ============== 会话管理（P0 新增） ==============


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions(
    current_user: CorePrincipal = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> SessionListResponse:
    """当前用户活跃会话列表（设备管理）。"""
    auth = AuthService(session)
    sessions = await auth.list_sessions(current_user.id)
    return SessionListResponse(sessions=sessions)


@router.delete("/sessions/{session_id}")
async def revoke_session(
    session_id: UUID,
    current_user: CorePrincipal = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """撤销指定会话（校验属主）。"""
    auth = AuthService(session)
    ok = await auth.revoke_session_by_id(current_user.id, session_id)
    if not ok:
        raise NotFoundError("会话不存在或已撤销")
    await session.commit()
    return {"success": True}


@router.post("/logout-all")
async def logout_all(
    current_user: CorePrincipal = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """退出所有设备：撤销当前用户全部 refresh token。"""
    auth = AuthService(session)
    revoked = await auth.revoke_all_user_tokens(current_user.id)
    await session.commit()
    return {"success": True, "revoked": revoked}


# ============== 冻结端点（packages/quota 未接入） ==============


@router.get("/quota", response_model=QuotaStatus)
async def quota() -> QuotaStatus:
    """配额状态：packages/quota 后续接入，冻结（无需鉴权）。"""
    raise _quota_frozen()