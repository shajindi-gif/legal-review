"""鉴权 API - 注册/登录/刷新/当前用户/登出 + M0 手机号注册。

所有路由前缀：/api/v1/auth
"""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.constants import OrganizationType, PlanTier, UserRole, UserStatus
from app.core.errors import ConflictError, RateLimitedError, ValidationError
from app.db.session import get_db
from app.models.user import Organization, User, UserPlan
from app.schemas.auth import (
    LoginRequest,
    PhoneRegisterRequest,
    PhoneRegisterResponse,
    QuotaStatus,
    RefreshRequest,
    RegisterRequest,
    SmsSendRequest,
    SmsSendResponse,
    TokenResponse,
    UserOut,
)
from app.services.audit import AuditService
from app.services.auth_service import AuthService, hash_password
from app.services.quota_service import QuotaService
from app.services.rate_limit import check_and_incr
from app.services.verification import VerificationService
from app.utils.phone import mask_phone, normalize_phone

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


# ============== M0: 密码强度校验 ==============

def _validate_password_strength(pw: str) -> None:
    """M0 弱密码拒绝: 至少 8 位 + 字母 + 数字。中文友好(不要求特殊字符)。"""
    if len(pw) < 8:
        raise ValidationError("密码至少 8 位")
    if not any(c.isalpha() for c in pw):
        raise ValidationError("密码需包含字母")
    if not any(c.isdigit() for c in pw):
        raise ValidationError("密码需包含数字")


# ============== M0: 手机号注册底层 ==============

async def _register_by_phone_internal(
    session: AsyncSession,
    *,
    phone: str,
    password: str,
    real_name: str | None,
    company: str | None,
) -> User:
    """手机号注册核心: phone 已归一化, password 已校验强度, 验证码已校验。

    逻辑:
    - 查 phone 是否已存在 (User.phone 唯一性)
    - username 从 phone 派生, 冲突时加 4 位后缀
    - email 留 None (M0 不强求)
    - 创建 Free 套餐 + 个人虚拟组织
    """
    # phone 唯一性预检
    existing = await session.scalar(select(User).where(User.phone == phone))
    if existing is not None:
        raise ConflictError("该手机号已注册")

    # username 派生: +8613800138000 → user_13800138000_<4位>
    suffix = phone.replace("+", "").replace("86", "", 1) if phone.startswith("+86") else phone
    base_username = f"u_{suffix[-11:]}"  # 取最后 11 位
    username = base_username

    for _ in range(5):
        chk = await session.scalar(select(User).where(User.username == username))
        if chk is None:
            break
        username = f"{base_username}{uuid4().hex[:4]}"
    else:
        raise ConflictError("用户名生成失败, 请重试")

    # 个人虚拟组织
    personal_org = Organization(
        name=f"{username} 个人工作台",
        type=OrganizationType.PERSONAL,
        status="active",
    )
    session.add(personal_org)
    await session.flush()

    now_naive = datetime.now(UTC).replace(tzinfo=None)
    user = User(
        username=username,
        real_name=real_name or f"用户{suffix[-4:]}",
        email=None,
        phone=phone,
        password_hash=hash_password(password),
        role=UserRole.SUBMITTER,
        company=company,
        status=UserStatus.ACTIVE,
        phone_verified_at=now_naive,  # M0: 验证码通过即视为已验证
        password_changed_at=now_naive,
        agreed_terms_at=now_naive,  # M0: 提交注册即视为同意 (后续可拆分)
    )
    user.organization_id = personal_org.id
    session.add(user)
    try:
        await session.flush()
    except IntegrityError as e:
        await session.rollback()
        raise ConflictError("注册失败: 手机号或用户名冲突") from e

    # Free 套餐
    plan = UserPlan(
        user_id=user.id,
        tier=PlanTier.FREE,
        status="active",
        quota_daily=3,
        used_today=0,
        quota_reset_date=now_naive.strftime("%Y-%m-%d"),
    )
    session.add(plan)
    await session.flush()
    await session.refresh(user, attribute_names=["plan"])
    return user


# ============== 邮箱注册 (沿用) ==============

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


# ============== M0: 手机号注册 ==============


@router.post("/sms/send", response_model=SmsSendResponse)
async def sms_send(
    body: SmsSendRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> dict:
    """M0: 发送手机验证码。

    限流:
    - IP 维度: 5 次/10 分钟 (Redis, 失败降级内存)
    - 手机号 60s 冷却 / 10/天 (在 VerificationService 内部用 DB 校验)
    """
    # 1. 归一化手机号 (格式不对直接 422)
    try:
        phone = normalize_phone(body.phone)
    except ValidationError:
        raise

    # 2. IP 维度限流 (Redis, 防止 IP 维度短信轰炸)
    client_ip = request.client.host if request.client else "unknown"
    await check_and_incr(scope="sms_send_ip", key=client_ip, limit=5, window_seconds=600)

    # 3. 调 VerificationService (内部再做手机号维度限流 + 落库 + 发送)
    svc = VerificationService(session)
    result = await svc.send_code(
        target=phone,
        channel="sms",
        purpose=body.purpose,
        ip_address=client_ip,
        user_agent=request.headers.get("user-agent"),
    )
    await session.commit()
    return SmsSendResponse(
        success=True,
        expires_in=result.expires_in,
        mock_code=result.mock_code,
    ).model_dump()


@router.post("/register/phone", response_model=PhoneRegisterResponse, status_code=201)
async def register_phone(
    body: PhoneRegisterRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> dict:
    """M0: 手机号注册。

    流程:
    1. 归一化手机号
    2. IP 限流 (防批量注册)
    3. 校验密码强度
    4. 校验验证码
    5. 创建 User (phone_verified_at = now)
    6. 签发 Token
    """
    client_ip = request.client.host if request.client else "unknown"

    # 1. 归一化
    phone = normalize_phone(body.phone)

    # 2. IP 限流 (10 次/小时/IP)
    await check_and_incr(scope="register_phone_ip", key=client_ip, limit=10, window_seconds=3600)

    # 3. 密码强度
    _validate_password_strength(body.password)

    # 4. 验证码校验
    vcode = VerificationService(session)
    await vcode.verify(target=phone, code=body.code, purpose="register")

    # 5. 创建用户
    user = await _register_by_phone_internal(
        session,
        phone=phone,
        password=body.password,
        real_name=body.real_name,
        company=body.company,
    )

    # 6. 审计 + 签发 token
    audit = AuditService(session)
    await audit.log(
        action="create",
        actor_id=user.id,
        actor_role=str(user.role),
        target_type="user",
        target_id=user.id,
        ip_address=client_ip,
        user_agent=request.headers.get("user-agent"),
    )
    auth = AuthService(session)
    tokens = auth.issue_tokens(user)
    await session.commit()

    return PhoneRegisterResponse(
        user_id=str(user.id),
        phone=mask_phone(phone),
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"],
        token_type=tokens["token_type"],
        expires_in=tokens["expires_in"],
    ).model_dump()
