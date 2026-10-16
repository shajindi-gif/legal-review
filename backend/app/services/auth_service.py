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

import hashlib
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

import bcrypt
import jwt

# ============== 密码哈希 (Argon2id + bcrypt 双算法兼容) ==============
# bcrypt 历史哈希 (老用户, 由 0003 之前的数据)
# argon2id 哈希 (M0 之后的新用户, 优先)
#
# 哈希前缀约定:
#   $argon2id$...  → Argon2id
#   $2b$ / $2a$    → bcrypt
#
# opportunistic rehash: 登录成功时若命中 bcrypt, 后台异步重哈希为 Argon2id
import structlog
from sqlalchemy import CursorResult, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.constants import FREE_TRIAL_LIMIT, OrganizationType, PlanTier, UserRole, UserStatus
from app.core.errors import AuthError, ConflictError, NotFoundError, ValidationError
from app.models.identity import RefreshToken
from app.models.user import Organization, User, UserPlan
from app.utils.phone import normalize_email, normalize_phone

try:
    from argon2 import PasswordHasher as _Argon2PasswordHasher
    from argon2.exceptions import (
        InvalidHashError,
        VerifyMismatchError,
    )
    _HAS_ARGON2 = True
except ImportError:  # noqa: BLE001
    _HAS_ARGON2 = False
    _Argon2PasswordHasher = None  # type: ignore[assignment,misc]
    InvalidHashError = Exception  # type: ignore[assignment,misc]
    VerifyMismatchError = Exception  # type: ignore[assignment,misc]


_log = structlog.get_logger("auth.password")
_argon2_hasher = _Argon2PasswordHasher() if _HAS_ARGON2 else None


def hash_password(plain: str) -> str:
    """新用户统一使用 Argon2id, 失败时回退 bcrypt (确保历史路径继续工作)。"""
    hasher = _argon2_hasher
    if _HAS_ARGON2 and hasher is not None:
        try:
            return hasher.hash(plain)
        except Exception:  # noqa: BLE001
            _log.warning("argon2_hash_failed_fallback_bcrypt")
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(plain.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """根据哈希前缀自动选择算法; 始终不会抛异常。"""
    if not hashed:
        return False
    if (
        hashed.startswith("$argon2id$")
        or hashed.startswith("$argon2i$")
        or hashed.startswith("$argon2$")
    ):
        if not _HAS_ARGON2:
            _log.error("argon2_hash_present_but_lib_missing")
            return False
        hasher = _argon2_hasher
        if hasher is None:
            return False
        try:
            hasher.verify(hashed, plain)
            return True
        except VerifyMismatchError:
            return False
        except (InvalidHashError, Exception):  # noqa: BLE001
            return False
    if hashed.startswith("$2"):
        try:
            return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
        except (ValueError, TypeError):
            return False
    return False


def is_legacy_bcrypt(hashed: str) -> bool:
    """是否使用旧 bcrypt, 用于登录成功后做 opportunistic rehash。"""
    return bool(hashed) and hashed.startswith("$2")


def needs_rehash(hashed: str) -> bool:
    """是否需要把 hash 升级到当前推荐算法。"""
    if not _HAS_ARGON2:
        return False
    if hashed.startswith("$argon2id$"):
        hasher = _argon2_hasher
        if hasher is None:
            return True
        try:
            return hasher.check_needs_rehash(hashed)
        except (InvalidHashError, Exception):  # noqa: BLE001
            return True
    return True


def opportunistic_rehash(user: User, plain: str) -> str | None:
    """登录成功后调用: 旧 bcrypt 用户自动升级到 Argon2id。

    返回新 hash 字符串 (调用方负责写回 DB), 不需要升级则返回 None。
    """
    if not is_legacy_bcrypt(user.password_hash) and not needs_rehash(user.password_hash):
        return None
    new_hash = hash_password(plain)
    return new_hash


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
    """签发 refresh token（有效期与持久化 refresh_tokens.expires_at 对齐）。"""
    settings = get_settings()
    now = datetime.now(UTC)
    ttl_seconds = settings.refresh_token_ttl_days * 86400
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "jti": uuid4().hex,
        "iat": int(now.timestamp()),
        "exp": int(now.timestamp()) + ttl_seconds,
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
            quota_daily=FREE_TRIAL_LIMIT,
            used_today=0,
            free_trial_used=0,
            free_trial_limit=FREE_TRIAL_LIMIT,
        )
        self._session.add(plan)
        await self._session.flush()
        # 预加载 plan 关系,避免后续 issue_tokens 在同步上下文里 lazy-load 触发 MissingGreenlet
        await self._session.refresh(user, attribute_names=["plan"])
        return user

    async def authenticate(self, *, email: str, password: str) -> User:
        """邮箱 + 密码登录；返回 User。

        M0 增强:
        - 自动识别 argon2id / bcrypt 哈希
        - 登录成功后若 hash 是旧 bcrypt, 透明升级到 argon2id
        """
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

        # opportunistic rehash: 旧 bcrypt 升级到 argon2id
        new_hash = opportunistic_rehash(user, password)
        if new_hash is not None:
            user.password_hash = new_hash
            user.password_changed_at = datetime.now(UTC).replace(tzinfo=None)

        # 更新最后登录时间
        user.last_login_at = datetime.now(UTC).replace(tzinfo=None)
        await self._session.flush()
        await self._session.refresh(user, attribute_names=["plan"])
        return user

    async def authenticate_by_phone(self, *, phone: str, password: str) -> User:
        """手机号 + 密码登录 (M0 增量)。

        与 authenticate 行为一致:
        - 自动识别 argon2id / bcrypt
        - 登录成功后旧 bcrypt 透明升级
        - 仅 query 条件从 email 改为 phone (已归一化为 +86...)
        """
        from app.utils.phone import normalize_phone
        phone_norm = normalize_phone(phone)
        user = await self._session.scalar(select(User).where(User.phone == phone_norm))
        if user is None:
            raise AuthError("手机号或密码错误")
        if not verify_password(password, user.password_hash):
            raise AuthError("手机号或密码错误")
        if str(user.status) != str(UserStatus.ACTIVE):
            raise AuthError(f"账号状态异常: {user.status}")

        new_hash = opportunistic_rehash(user, password)
        if new_hash is not None:
            user.password_hash = new_hash
            user.password_changed_at = datetime.now(UTC).replace(tzinfo=None)

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
                quota_daily=FREE_TRIAL_LIMIT,
                used_today=0,
                free_trial_used=0,
                free_trial_limit=FREE_TRIAL_LIMIT,
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

    # ==========================================================
    # 统一账号：验证码登录/注册 + 持久化 RefreshToken（rotation/revoke）
    # ==========================================================

    async def login_or_register_by_identity(
        self,
        *,
        channel: str,
        target: str,
        real_name: str | None = None,
        company: str | None = None,
    ) -> tuple[User, bool]:
        """验证码校验通过后统一入口：已有身份登录原账号，新身份创建账号。

        channel: "phone" | "email"；target 已规范化（E.164 / 小写 email）。
        返回 (user, is_new_user)。
        """
        if channel == "phone":
            user = await self._session.scalar(select(User).where(User.phone == target))
        elif channel == "email":
            user = await self._session.scalar(select(User).where(User.email == target))
        else:
            raise ValidationError(f"不支持的 channel: {channel}")

        if user is not None:
            if str(user.status) != str(UserStatus.ACTIVE):
                raise AuthError(f"账号状态异常: {user.status}")
            user.last_login_at = datetime.now(UTC).replace(tzinfo=None)
            await self._session.flush()
            await self._session.refresh(user, attribute_names=["plan"])
            return user, False

        # 新身份 → 创建账号（个人虚拟组织 + Free 套餐）
        username_base = (
            target.rsplit("@", 1)[0] if channel == "email" else "u" + target[-9:]
        )
        username = username_base
        for _ in range(5):
            chk = await self._session.scalar(
                select(User).where(User.username == username)
            )
            if chk is None:
                break
            username = f"{username_base}-{uuid4().hex[:4]}"
        else:  # noqa: SIM110
            raise ConflictError("用户名生成失败，请重试")

        personal_org = Organization(
            name=f"{username} 个人工作台",
            type=OrganizationType.PERSONAL,
            status="active",
        )
        self._session.add(personal_org)
        await self._session.flush()

        user = User(
            username=username,
            real_name=real_name or username_base[:64],
            email=target if channel == "email" else None,
            phone=target if channel == "phone" else None,
            password_hash="",  # 验证码账号无密码（密码作为兼容入口可后续设置）
            role=UserRole.SUBMITTER,
            company=company,
            status=UserStatus.ACTIVE,
        )
        user.organization_id = personal_org.id
        if channel == "email":
            user.email_verified_at = datetime.now(UTC)
        else:
            user.phone_verified_at = datetime.now(UTC)
        self._session.add(user)
        try:
            await self._session.flush()
        except IntegrityError as e:
            await self._session.rollback()
            raise ConflictError("注册失败：手机号或邮箱已存在") from e

        plan = UserPlan(
            user_id=user.id,
            tier=PlanTier.FREE,
            status="active",
            quota_daily=FREE_TRIAL_LIMIT,
            used_today=0,
            free_trial_used=0,
            free_trial_limit=FREE_TRIAL_LIMIT,
        )
        self._session.add(plan)
        await self._session.flush()
        await self._session.refresh(user, attribute_names=["plan"])
        return user, True

    # ---------- 持久化 refresh token（rotation + revoke） ----------

    @staticmethod
    def _hash_token(raw: str) -> str:
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _refresh_expiry(refresh_token: str) -> datetime:
        payload = decode_token(refresh_token)
        return datetime.fromtimestamp(int(payload["exp"]), tz=UTC)

    async def issue_token_pair(
        self,
        user: User,
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
        device_id: str | None = None,
    ) -> dict:
        """签发 access + refresh，并把 refresh 持久化（hash 落库）。"""
        tier = PlanTier.FREE
        if user.plan is not None:
            tier = user.plan.tier
        access = create_access_token(user.id, str(user.role), str(tier))
        refresh_raw = create_refresh_token(user.id)

        rt = RefreshToken(
            id=uuid4(),
            user_id=user.id,
            token_hash=self._hash_token(refresh_raw),
            expires_at=self._refresh_expiry(refresh_raw),
            ip_address=ip_address,
            user_agent=user_agent,
            device_id=device_id,
        )
        self._session.add(rt)
        await self._session.flush()

        settings = get_settings()
        return {
            "access_token": access,
            "refresh_token": refresh_raw,
            "token_type": "bearer",
            "expires_in": settings.jwt_access_ttl,
        }

    async def refresh_token_pair(
        self,
        refresh_token: str,
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> dict:
        """refresh 轮换：旧 token 作废 + 标记 replaced_by，签发新对。"""
        payload = decode_token(refresh_token)
        if payload.get("type") != "refresh":
            raise AuthError("非 refresh token")
        token_hash = self._hash_token(refresh_token)

        rt = await self._session.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        if rt is None or rt.revoked_at is not None:
            raise AuthError("刷新令牌已失效")
        if rt.expires_at <= datetime.now(UTC):
            raise AuthError("刷新令牌已过期")

        user = await self.get_user_by_id(rt.user_id)
        if str(user.status) != str(UserStatus.ACTIVE):
            raise AuthError("账号状态异常")

        # 轮换：作废旧 token
        rt.revoked_at = datetime.now(UTC)
        rt.revoke_reason = "rotation"
        await self._session.flush()

        pair = await self.issue_token_pair(
            user, ip_address=ip_address, user_agent=user_agent
        )
        # 关联新 token
        new_hash = self._hash_token(pair["refresh_token"])
        new_rt = await self._session.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == new_hash)
        )
        if new_rt is not None:
            rt.replaced_by_id = new_rt.id
            await self._session.flush()
        return pair

    async def revoke_refresh_token(self, refresh_token: str) -> None:
        """登出：撤销单个 refresh token（幂等）。"""
        token_hash = self._hash_token(refresh_token)
        rt = await self._session.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        if rt is not None and rt.revoked_at is None:
            rt.revoked_at = datetime.now(UTC)
            rt.revoke_reason = "logout"
            await self._session.flush()

    async def revoke_all_user_tokens(self, user_id: UUID) -> int:
        """安全中心：撤销该用户所有未撤销的 refresh token，返回撤销数量。"""
        now = datetime.now(UTC)
        result = await self._session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now, revoke_reason="logout_all")
        )
        await self._session.flush()
        return cast(CursorResult[Any], result).rowcount or 0

    async def list_sessions(self, user_id: UUID) -> list[dict]:
        """列出用户未撤销的会话（refresh token）。"""
        rows = (
            await self._session.execute(
                select(RefreshToken)
                .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
                .order_by(RefreshToken.issued_at.desc())
            )
        ).scalars().all()
        now = datetime.now(UTC)
        out: list[dict] = []
        for rt in rows:
            if rt.expires_at <= now:
                continue
            out.append(
                {
                    "id": str(rt.id),
                    "issued_at": rt.issued_at,
                    "expires_at": rt.expires_at,
                    "user_agent": rt.user_agent,
                    "ip_address": None if rt.ip_address is None else str(rt.ip_address),
                    "device_id": rt.device_id,
                }
            )
        return out

    async def revoke_session_by_id(self, user_id: UUID, session_id: UUID) -> bool:
        """撤销指定会话（校验属主，防越权）。返回是否实际撤销。"""
        rt = await self._session.get(RefreshToken, session_id)
        if rt is None or rt.user_id != user_id or rt.revoked_at is not None:
            return False
        rt.revoked_at = datetime.now(UTC)
        rt.revoke_reason = "user_revoke"
        await self._session.flush()
        return True

    async def revoke_other_user_tokens(self, user_id: UUID, keep_raw: str) -> int:
        """撤销除 keep_raw 对应会话外的所有未撤销 refresh token（改密码场景保留当前设备）。"""
        keep_hash = self._hash_token(keep_raw)
        now = datetime.now(UTC)
        result = await self._session.execute(
            update(RefreshToken)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.token_hash != keep_hash,
            )
            .values(revoked_at=now, revoke_reason="password_changed")
        )
        await self._session.flush()
        return cast(CursorResult[Any], result).rowcount or 0

    # ---------- 密码管理（P0 升级） ----------

    async def set_password(self, user: User, new_password: str) -> None:
        """直接设置新密码（重置密码场景，调用方已完成验证码校验）。"""
        user.password_hash = hash_password(new_password)
        user.password_changed_at = datetime.now(UTC).replace(tzinfo=None)
        user.failed_login_count = 0
        user.locked_until = None
        await self._session.flush()

    async def change_password(
        self, user: User, current_password: str, new_password: str
    ) -> None:
        """修改密码：校验当前密码 → 写入新 hash。失败抛 AuthError。"""
        if not user.password_hash or not verify_password(current_password, user.password_hash):
            raise AuthError("当前密码错误")
        if current_password == new_password:
            raise ValidationError("新密码不能与当前密码相同")
        await self.set_password(user, new_password)

    async def authenticate_by_identifier(
        self, *, identifier: str, password: str
    ) -> User:
        """统一身份密码登录：identifier 自动识别邮箱 / 手机号（本地账号）。

        防枚举：不存在与密码错误统一文案「邮箱/手机号或密码错误」。
        """
        ident = identifier.strip()
        if "@" in ident:
            email_norm = normalize_email(ident)
            user = await self._session.scalar(select(User).where(User.email == email_norm))
        else:
            phone_norm = normalize_phone(ident)
            user = await self._session.scalar(select(User).where(User.phone == phone_norm))
        if user is None or not user.password_hash:
            raise AuthError("账号或密码错误")
        if not verify_password(password, user.password_hash):
            raise AuthError("账号或密码错误")
        if str(user.status) != str(UserStatus.ACTIVE):
            raise AuthError(f"账号状态异常: {user.status}")

        new_hash = opportunistic_rehash(user, password)
        if new_hash is not None:
            user.password_hash = new_hash
            user.password_changed_at = datetime.now(UTC).replace(tzinfo=None)
        user.last_login_at = datetime.now(UTC).replace(tzinfo=None)
        await self._session.flush()
        await self._session.refresh(user, attribute_names=["plan"])
        return user

    async def find_by_email(self, email: str) -> User | None:
        """按邮箱查找用户（内部用，不抛枚举信息）。"""
        user: User | None = await self._session.scalar(select(User).where(User.email == email))
        return user

    async def bind_identity(self, user: User, *, channel: str, target: str) -> str:
        """绑定/换绑手机号或邮箱（验证码已由调用方校验）。

        返回归一化后的 target。目标已被其他账户占用时抛 ConflictError。
        """
        if channel == "phone":
            occupant = await self._session.scalar(select(User).where(User.phone == target))
        elif channel == "email":
            occupant = await self._session.scalar(select(User).where(User.email == target))
        else:
            raise ValidationError(f"不支持的 channel: {channel}")

        if occupant is not None and occupant.id != user.id:
            raise ConflictError(f"该{'手机号' if channel == 'phone' else '邮箱'}已被其他账户绑定")

        if channel == "phone":
            user.phone = target
            user.phone_verified_at = datetime.now(UTC)
        else:
            user.email = target
            user.email_verified_at = datetime.now(UTC)
        await self._session.flush()
        return target
