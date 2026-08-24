"""鉴权服务 - bcrypt 密码哈希 + JWT 签发/校验 + 用户注册/登录。

JWT 结构（HS256）:
  payload = {
    "sub": user_id (str),
    "role": role,
    "tier": plan_tier,
    "type": "access" | "refresh",
    "exp": unix_ts,
    "iat": unix_ts,
  }
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import bcrypt
import jwt
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.constants import OrganizationType, PlanTier, UserRole, UserStatus
from app.core.errors import AuthError, ConflictError, NotFoundError
from app.models.user import Organization, User, UserPlan

# ============== 密码哈希 ==============


def hash_password(plain: str) -> str:
    """bcrypt 哈希密码（cost=12）。"""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(plain.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """校验明文密码与哈希是否匹配。"""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ============== JWT ==============

_ALGORITHM = "HS256"


def create_access_token(user_id: UUID, role: str, tier: str = PlanTier.FREE) -> str:
    """签发 access token。"""
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "role": str(role),
        "tier": str(tier),
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int(now.timestamp()) + settings.jwt_access_ttl,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=_ALGORITHM)


def create_refresh_token(user_id: UUID) -> str:
    """签发 refresh token。"""
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "iat": int(now.timestamp()),
        "exp": int(now.timestamp()) + settings.jwt_refresh_ttl,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=_ALGORITHM)


def decode_token(token: str) -> dict:
    """解码并校验 JWT；失败抛 AuthError。"""
    settings = get_settings()
    try:
        payload: dict = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[_ALGORITHM],
        )
    except jwt.ExpiredSignatureError as e:
        msg = "Token 已过期"
        raise AuthError(msg) from e
    except jwt.InvalidTokenError as e:
        msg = "Token 无效"
        raise AuthError(msg) from e
    return payload


# ============== AuthService ==============


class AuthService:
    """用户注册 / 登录 / Token 管理。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def register(
        self,
        *,
        email: str,
        password: str,
        company: str | None = None,
        real_name: str | None = None,
    ) -> User:
        """注册新用户：创建 User + Free 版 UserPlan。

        - username 取 email 本地部分（@ 前），冲突时追加 4 位随机后缀
        - role 默认 submitter
        - 自动创建 Free 套餐（每天 3 次）
        """
        # email 唯一性预检
        existing = await self._session.scalar(
            select(User).where(User.email == email)
        )
        if existing is not None:
            msg = f"邮箱 {email} 已注册"
            raise ConflictError(msg)

        username_base = email.split("@")[0]
        username = username_base
        # username 唯一性兜底
        for _ in range(5):
            chk = await self._session.scalar(
                select(User).where(User.username == username)
            )
            if chk is None:
                break
            username = f"{username_base}{uuid4().hex[:4]}"
        else:  # noqa: SIM110 - 5 次仍冲突
            msg = "用户名生成失败，请重试"
            raise ConflictError(msg)

        user = User(
            username=username,
            real_name=real_name or username_base,
            email=email,
            password_hash=hash_password(password),
            role=UserRole.SUBMITTER,
            company=company,
            status=UserStatus.ACTIVE,
        )

        # SaaS：注册时自动创建"个人虚拟组织"（PERSONAL type），让送审链路
        # 永远有 organization_id 可挂。后续 Pro/Enterprise 升级或企业邀请时，
        # 可在管理后台把 user.organization_id 改到目标 org。
        personal_org = Organization(
            name=f"{username} 个人工作台",
            type=OrganizationType.PERSONAL,
            status="active",
        )
        self._session.add(personal_org)
        await self._session.flush()
        user.organization_id = personal_org.id

        self._session.add(user)
        try:
            await self._session.flush()
        except IntegrityError as e:
            await self._session.rollback()
            msg = "注册失败：邮箱或用户名冲突"
            raise ConflictError(msg) from e

        # 创建 Free 套餐
        plan = UserPlan(
            user_id=user.id,
            tier=PlanTier.FREE,
            status="active",
            quota_daily=3,
            used_today=0,
            quota_reset_date=datetime.now(UTC).strftime("%Y-%m-%d"),
        )
        self._session.add(plan)
        await self._session.flush()
        # 预加载 plan 关系,避免后续 issue_tokens 在同步上下文里 lazy-load 触发 MissingGreenlet
        await self._session.refresh(user, attribute_names=["plan"])
        return user

    async def authenticate(self, *, email: str, password: str) -> User:
        """邮箱 + 密码登录；返回 User。"""
        user = await self._session.scalar(select(User).where(User.email == email))
        if user is None:
            msg = "邮箱或密码错误"
            raise AuthError(msg)
        if not verify_password(password, user.password_hash):
            msg = "邮箱或密码错误"
            raise AuthError(msg)
        if str(user.status) != str(UserStatus.ACTIVE):
            msg = f"账号状态异常: {user.status}"
            raise AuthError(msg)
        # 更新最后登录时间
        user.last_login_at = datetime.now(UTC).replace(tzinfo=None)
        await self._session.flush()
        await self._session.refresh(user, attribute_names=["plan"])
        return user

    async def get_user_by_id(self, user_id: UUID) -> User:
        """按 ID 查询用户。"""
        user = await self._session.get(User, user_id)
        if user is None:
            msg = "用户不存在"
            raise NotFoundError(msg)
        await self._session.refresh(user, attribute_names=["plan"])
        return user

    async def get_user_plan(self, user_id: UUID) -> UserPlan:
        """查询用户套餐；不存在则创建 Free 兜底。"""
        plan = await self._session.scalar(
            select(UserPlan).where(UserPlan.user_id == user_id)
        )
        if plan is None:
            plan = UserPlan(
                user_id=user_id,
                tier=PlanTier.FREE,
                status="active",
                quota_daily=3,
                used_today=0,
            )
            self._session.add(plan)
            await self._session.flush()
        return plan

    def issue_tokens(self, user: User) -> dict:
        """为已认证用户签发 access + refresh token。"""
        tier = PlanTier.FREE
        # plan 可能在 selectin 关系中已加载
        if user.plan is not None:
            tier = user.plan.tier
        access = create_access_token(user.id, str(user.role), str(tier))
        refresh = create_refresh_token(user.id)
        settings = get_settings()
        return {
            "access_token": access,
            "refresh_token": refresh,
            "token_type": "bearer",
            "expires_in": settings.jwt_access_ttl,
        }

    async def refresh_access(self, refresh_token: str) -> dict:
        """用 refresh token 换取新的 access token。"""
        payload = decode_token(refresh_token)
        if payload.get("type") != "refresh":
            msg = "非 refresh token"
            raise AuthError(msg)
        user_id = UUID(payload["sub"])
        user = await self.get_user_by_id(user_id)
        if str(user.status) != str(UserStatus.ACTIVE):
            msg = "账号状态异常"
            raise AuthError(msg)
        return self.issue_tokens(user)
