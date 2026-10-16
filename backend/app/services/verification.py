"""Verification Code Service。

M0 职责:
- 生成 6 位数字验证码
- bcrypt 哈希后落库 (verification_codes)
- 调 SMSProvider 发送
- 校验: 一次性, 5 分钟过期, 5 次错误作废
- 发送频率限制: 60s/phone, 5/10min/ip, 10/天/phone

非 M0 范围:
- 邮箱验证码
- 滑块 / reCAPTCHA
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import bcrypt
import structlog
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import CodeError, RateLimitedError, ValidationError
from app.models.identity import VerificationCode
from app.services.email import EmailProvider, get_email_provider
from app.services.sms import SMSProvider, get_sms_provider
from app.utils.phone import mask_email, mask_phone, normalize_email

_log = structlog.get_logger("auth.verification")

# ============== 限制常量 (M0) ==============
CODE_LENGTH = 6
CODE_TTL_SECONDS = 300            # 5 分钟
PER_PHONE_COOLDOWN_SECONDS = 60   # 60s 内不能重发
PER_IP_WINDOW_SECONDS = 600       # 10 分钟窗口
PER_IP_MAX_SENDS = 5              # 5 次 / 10min / IP
PER_PHONE_DAILY_MAX = 10          # 10 次 / 天 / 手机号
MAX_VERIFY_ATTEMPTS = 5           # 5 次错误作废

VALID_PURPOSES = frozenset({
    "register", "login", "reset_password",
    "bind_phone", "change_phone", "bind_email", "change_email",
})


@dataclass
class SendResult:
    """发送结果。"""
    expires_in: int
    mock_code: str | None = None  # 仅 mock 模式


class VerificationService:
    """验证码生成 / 发送 / 校验。"""

    def __init__(
        self,
        session: AsyncSession,
        sms: SMSProvider | None = None,
        email: EmailProvider | None = None,
        *,
        settings: Any = None,
    ) -> None:
        self._session = session
        self._sms = sms or get_sms_provider()
        self._email = email or get_email_provider()
        # 阈值接线到配置（config.py verification_*），缺省回退模块常量（测试兼容）
        if settings is None:
            from app.core.config import get_settings
            settings = get_settings()
        self.code_ttl = (
            getattr(settings, "verification_code_ttl_seconds", None) or CODE_TTL_SECONDS
        )
        self.max_attempts = (
            getattr(settings, "verification_code_max_attempts", None) or MAX_VERIFY_ATTEMPTS
        )
        self.cooldown_seconds = (
            getattr(settings, "verification_per_target_cooldown_seconds", None)
            or PER_PHONE_COOLDOWN_SECONDS
        )
        self.ip_window_seconds = (
            getattr(settings, "verification_per_ip_window_seconds", None) or PER_IP_WINDOW_SECONDS
        )
        self.ip_max_sends = (
            getattr(settings, "verification_per_ip_max_sends", None) or PER_IP_MAX_SENDS
        )
        self.target_daily_max = (
            getattr(settings, "verification_per_target_daily_max", None) or PER_PHONE_DAILY_MAX
        )

    @staticmethod
    def _generate_code() -> str:
        """6 位数字验证码。"""
        return f"{secrets.randbelow(10**CODE_LENGTH):0{CODE_LENGTH}d}"

    @staticmethod
    def _hash_code(code: str) -> str:
        """bcrypt 哈希验证码 (cost=10, 比密码 cost=12 略低, 验证码场景可接受)。"""
        return bcrypt.hashpw(code.encode("utf-8"), bcrypt.gensalt(rounds=10)).decode("utf-8")

    @staticmethod
    def _verify_code_hash(plain: str, hashed: str) -> bool:
        try:
            return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
        except (ValueError, TypeError):
            return False

    # ==========================================================
    # 发送验证码
    # ==========================================================
    async def send_code(
        self,
        *,
        target: str,
        channel: str = "sms",
        purpose: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> SendResult:
        """生成并发送验证码。失败抛 RateLimitedError / ValidationError。"""
        if channel not in ("sms", "email"):
            raise ValidationError(f"不支持的 channel: {channel}")
        if purpose not in VALID_PURPOSES:
            raise ValidationError(f"不支持的 purpose: {purpose}")
        if channel == "sms" and not target:
            raise ValidationError("手机号不能为空")
        if channel == "email":
            target = normalize_email(target)

        now = datetime.now(UTC).replace(tzinfo=None)

        # ---- 限流 1: 同手机号 60s 内不能重发 ----
        last_cooldown = now - timedelta(seconds=self.cooldown_seconds)
        recent = await self._session.scalar(
            select(VerificationCode)
            .where(
                and_(
                    VerificationCode.target == target,
                    VerificationCode.purpose == purpose,
                    VerificationCode.created_at > last_cooldown,
                )
            )
            .order_by(VerificationCode.created_at.desc())
            .limit(1)
        )
        if recent is not None:
            remaining = self.cooldown_seconds - int((now - recent.created_at).total_seconds())
            _log.info(
                "verify_code_cooldown",
                target=mask_phone(target),
                purpose=purpose,
                remaining=remaining,
            )
            raise RateLimitedError(
                f"请 {max(1, remaining)} 秒后再试",
            )

        # ---- 限流 2: 单 IP 5/10min ----
        if ip_address:
            window_start = now - timedelta(seconds=self.ip_window_seconds)
            ip_count = await self._session.scalar(
                select(func.count(VerificationCode.id))
                .where(
                    and_(
                        VerificationCode.ip_address == ip_address,
                        VerificationCode.created_at > window_start,
                    )
                )
            )
            if ip_count is not None and ip_count >= self.ip_max_sends:
                _log.warning("verify_code_ip_rate_limit", ip=ip_address, count=ip_count)
                raise RateLimitedError()

        # ---- 限流 3: 单手机号 10/天 ----
        day_start = now - timedelta(hours=24)
        day_count = await self._session.scalar(
            select(func.count(VerificationCode.id))
            .where(
                and_(
                    VerificationCode.target == target,
                    VerificationCode.created_at > day_start,
                )
            )
        )
        if day_count is not None and day_count >= self.target_daily_max:
            _log.warning("verify_code_daily_limit", target=mask_phone(target), count=day_count)
            raise RateLimitedError("今日发送次数已达上限, 明天再试")

        # ---- 生成 + 落库 + 发送 ----
        code = self._generate_code()
        code_hash = self._hash_code(code)
        expires_at = now + timedelta(seconds=self.code_ttl)

        row = VerificationCode(
            id=uuid4(),
            target=target,
            channel=channel,
            purpose=purpose,
            code_hash=code_hash,
            expires_at=expires_at,
            attempt_count=0,
            max_attempts=self.max_attempts,
            used_at=None,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self._session.add(row)
        await self._session.flush()

        # ---- 发送 ----
        mock_code: str | None = None
        if channel == "sms":
            sms_result = await self._sms.send_code(
                phone=target,
                code=code,
                purpose=purpose,
                ttl_seconds=self.code_ttl,
            )
            if not sms_result.success:
                _log.error(
                    "sms_send_failed",
                    target=mask_phone(target),
                    error=sms_result.error_message,
                )
                raise CodeError("sms_send_failed", "短信发送失败, 请稍后重试", http_status=502)
            mock_code = sms_result.mock_code
        else:
            email_result = await self._email.send_code(
                email=target,
                code=code,
                purpose=purpose,
                ttl_seconds=self.code_ttl,
            )
            if not email_result.success:
                _log.error(
                    "email_send_failed",
                    target=mask_email(target),
                    error=email_result.error_message,
                )
                raise CodeError("email_send_failed", "邮件发送失败, 请稍后重试", http_status=502)
            mock_code = email_result.mock_code

        masked = mask_phone(target) if channel == "sms" else mask_email(target)
        _log.info(
            "verify_code_sent",
            target=masked,
            purpose=purpose,
            channel=channel,
            ttl=self.code_ttl,
        )

        return SendResult(expires_in=self.code_ttl, mock_code=mock_code)

    # ==========================================================
    # 校验验证码
    # ==========================================================
    async def verify(
        self,
        *,
        target: str,
        code: str,
        purpose: str,
    ) -> bool:
        """校验验证码; 成功 → used_at=now, 失败 → attempt_count++

        Returns:
            bool: 校验是否通过

        Raises:
            CodeError: 已过期 / 已用 / 错误次数超限 / 不存在
        """
        if not target or not code:
            raise CodeError("invalid_code", "验证码错误", http_status=400)

        # 找最新一条未使用未过期的
        now = datetime.now(UTC).replace(tzinfo=None)
        row = await self._session.scalar(
            select(VerificationCode)
            .where(
                and_(
                    VerificationCode.target == target,
                    VerificationCode.purpose == purpose,
                    VerificationCode.used_at.is_(None),
                )
            )
            .order_by(VerificationCode.created_at.desc())
            .limit(1)
        )
        if row is None:
            _log.info("verify_code_not_found", target=mask_phone(target), purpose=purpose)
            raise CodeError("invalid_code", "验证码错误或已失效", http_status=400)

        if row.expires_at < (
            now if row.expires_at.tzinfo is None else now.replace(tzinfo=row.expires_at.tzinfo)
        ):
            # 过期, 直接作废
            row.used_at = now
            await self._session.flush()
            _log.info("verify_code_expired", target=mask_phone(target), purpose=purpose)
            raise CodeError("code_expired", "验证码已过期, 请重新获取", http_status=400)

        if row.attempt_count >= row.max_attempts:
            row.used_at = now
            await self._session.flush()
            _log.warning(
                "verify_code_too_many_attempts",
                target=mask_phone(target),
                purpose=purpose,
            )
            raise CodeError("code_locked", "验证码错误次数过多, 请重新获取", http_status=400)

        # 比对
        if not self._verify_code_hash(code, row.code_hash):
            row.attempt_count += 1
            await self._session.flush()
            _log.info(
                "verify_code_wrong",
                target=mask_phone(target),
                purpose=purpose,
                attempt=row.attempt_count,
            )
            raise CodeError("invalid_code", "验证码错误", http_status=400)

        # 成功 → 标记使用
        row.used_at = now
        await self._session.flush()
        _log.info("verify_code_success", target=mask_phone(target), purpose=purpose)
        return True
