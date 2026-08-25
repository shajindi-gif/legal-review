"""生产级身份系统 ORM 模型 (0003 migration)。

包含:
- OAuthIdentity:       OAuth 登录方式绑定
- VerificationCode:    短信/邮箱验证码
- RefreshToken:        Refresh token 持久化（支持 rotation + revoke）
- UserLoginEvent:      登录审计
- UserAcquisitionSource: UTM 归因
- UserEvent:           通用事件埋点
- AccountLinkPending:  待合并账号队列
- RateLimitBucket:     应用层限流兜底

User 表的扩展字段在 models/user.py 中合并（M2 阶段统一更新）。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


# ============================================================
# T16 oauth_identities
# ============================================================
class OAuthIdentity(TimestampMixin, Base):
    """一个用户可以绑定多个 OAuth provider (GitHub / Google / WeChat)。"""

    __tablename__ = "oauth_identities"
    __table_args__ = (
        UniqueConstraint("provider", "provider_user_id", name="uq_oauth_provider_user"),
        Index("ix_oauth_user", "user_id"),
        Index("ix_oauth_provider_email", "provider", "provider_email"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True,
        server_default=sa.text("uuid_generate_v4()"),
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(16), nullable=False)
    provider_user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    provider_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_email_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa.text("false"),
    )
    provider_display_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    provider_avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Fernet 对称加密后存储
    access_token_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    refresh_token_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    scope: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_profile: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(nullable=True)

    user: Mapped[Any] = relationship(lazy="selectin")

    def __repr__(self) -> str:
        return f"<OAuthIdentity {self.provider}:{self.provider_user_id} user={self.user_id}>"


# ============================================================
# T17 verification_codes
# ============================================================
class VerificationCode(Base):
    """验证码：bcrypt 哈希落库；命中 / 过期 / 错误超限 → used_at=now。"""

    __tablename__ = "verification_codes"
    __table_args__ = (
        Index("ix_vc_target_purpose", "target", "purpose", sa.text("created_at DESC")),
        Index("ix_vc_expires", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True,
        server_default=sa.text("uuid_generate_v4()"),
    )
    target: Mapped[str] = mapped_column(String(64), nullable=False)
    channel: Mapped[str] = mapped_column(String(16), nullable=False)  # sms / email
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="5")
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ip_address: Mapped[Any | None] = mapped_column(INET, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sa.text("now()"),
    )

    def is_valid(self) -> bool:
        return self.used_at is None and self.attempt_count < self.max_attempts and self.expires_at > datetime.utcnow()

    def __repr__(self) -> str:
        return f"<VerificationCode {self.channel}:{self.purpose} target={self.target}>"


# ============================================================
# T18 refresh_tokens
# ============================================================
class RefreshToken(Base):
    """Refresh token 持久化：rotation + revoke。"""

    __tablename__ = "refresh_tokens"
    __table_args__ = (
        Index("ix_rt_user", "user_id"),
        Index("ix_rt_expires", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True,
        server_default=sa.text("uuid_generate_v4()"),
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sa.text("now()"),
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    replaced_by_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("refresh_tokens.id"),
        nullable=True,
    )
    revoke_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[Any | None] = mapped_column(INET, nullable=True)
    device_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sa.text("now()"),
    )

    def is_active(self) -> bool:
        return self.revoked_at is None and self.expires_at > datetime.utcnow()

    def __repr__(self) -> str:
        return f"<RefreshToken user={self.user_id} revoked={self.revoked_at is not None}>"


# ============================================================
# T19 user_login_events
# ============================================================
class UserLoginEvent(Base):
    """每次登录尝试都落库一份（成功 + 失败都记）。"""

    __tablename__ = "user_login_events"
    __table_args__ = (
        Index("ix_login_user_time", "user_id", sa.text("created_at DESC")),
        Index("ix_login_ip_time", "ip_address", sa.text("created_at DESC")),
        Index("ix_login_method_time", "login_method", sa.text("created_at DESC")),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True,
        server_default=sa.text("uuid_generate_v4()"),
    )
    user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    identifier: Mapped[str | None] = mapped_column(String(128), nullable=True)
    login_method: Mapped[str] = mapped_column(String(32), nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ip_address: Mapped[Any | None] = mapped_column(INET, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    device_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sa.text("now()"),
    )

    def __repr__(self) -> str:
        return f"<UserLoginEvent {self.login_method} success={self.success}>"


# ============================================================
# T20 user_acquisition_sources
# ============================================================
class UserAcquisitionSource(Base):
    """UTM 归因 + 首次访问来源。"""

    __tablename__ = "user_acquisition_sources"
    __table_args__ = (
        Index("ix_uas_utm_source", "utm_source"),
        Index("ix_uas_utm_campaign", "utm_campaign"),
    )

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    utm_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    utm_medium: Mapped[str | None] = mapped_column(String(64), nullable=True)
    utm_campaign: Mapped[str | None] = mapped_column(String(128), nullable=True)
    utm_content: Mapped[str | None] = mapped_column(String(128), nullable=True)
    utm_term: Mapped[str | None] = mapped_column(String(128), nullable=True)
    referrer: Mapped[str | None] = mapped_column(Text, nullable=True)
    landing_page: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sa.text("now()"),
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sa.text("now()"),
    )

    def __repr__(self) -> str:
        return f"<UserAcquisitionSource user={self.user_id} utm={self.utm_source}>"


# ============================================================
# T21 user_events
# ============================================================
class UserEvent(Base):
    """通用事件埋点；后续可异步转发到 PostHog / Mixpanel / GA4。"""

    __tablename__ = "user_events"
    __table_args__ = (
        Index("ix_event_name_time", "event_name", sa.text("created_at DESC")),
        Index("ix_event_user_time", "user_id", sa.text("created_at DESC")),
        Index("ix_event_anon_time", "anonymous_id", sa.text("created_at DESC")),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True,
        server_default=sa.text("uuid_generate_v4()"),
    )
    user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    anonymous_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_name: Mapped[str] = mapped_column(String(64), nullable=False)
    properties: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    ip_address: Mapped[Any | None] = mapped_column(INET, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sa.text("now()"),
    )

    def __repr__(self) -> str:
        return f"<UserEvent {self.event_name} user={self.user_id}>"


# ============================================================
# T22 account_link_pending
# ============================================================
class AccountLinkPending(Base):
    """当 OAuth email 命中已有 user 但 verified 状态不同时，进入待合并队列。"""

    __tablename__ = "account_link_pending"
    __table_args__ = (
        Index("ix_alp_user_state", "existing_user_id", "state"),
        Index("ix_alp_expires", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True,
        server_default=sa.text("uuid_generate_v4()"),
    )
    existing_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    new_provider: Mapped[str] = mapped_column(String(16), nullable=False)
    new_provider_user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    new_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    new_email_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa.text("false"),
    )
    new_raw_profile: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    state: Mapped[str] = mapped_column(String(32), nullable=False, server_default="waiting_confirm")
    confirm_token: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False, unique=True,
        server_default=sa.text("uuid_generate_v4()"),
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ip_address: Mapped[Any | None] = mapped_column(INET, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sa.text("now()"),
    )

    def __repr__(self) -> str:
        return f"<AccountLinkPending {self.new_provider} state={self.state}>"


# ============================================================
# T23 rate_limit_buckets
# ============================================================
class RateLimitBucket(Base):
    """DB 兜底限流；优先用 Redis，Redis 挂了降级到 DB。"""

    __tablename__ = "rate_limit_buckets"
    __table_args__ = (
        Index("ix_rlb_key_window", "bucket_key", "window_started_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    bucket_key: Mapped[str] = mapped_column(String(255), nullable=False)
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    max_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sa.text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sa.text("now()"),
    )

    def __repr__(self) -> str:
        return f"<RateLimitBucket {self.bucket_key} {self.count}/{self.max_count}>"
