"""用户、单位、订阅 ORM 模型。"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import (
    OrganizationType,
    PaymentStatus,
    PlanTier,
    SubscriptionStatus,
    UserRole,
    UserStatus,
)
from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPkMixin


class Organization(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, Base):
    """单位表 T02。"""

    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    type: Mapped[OrganizationType] = mapped_column(String(32), nullable=False)
    parent_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id"),
        nullable=True,
    )
    region_code: Mapped[str | None] = mapped_column(String(12), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")

    parent: Mapped[Organization | None] = relationship(
        "Organization", remote_side="Organization.id", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<Organization {self.name}>"


class User(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, Base):
    """用户表 T01。"""

    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    real_name: Mapped[str] = mapped_column(String(64), nullable=False)
    email: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(String(32), nullable=False)
    # SaaS：用户注册时填写的公司/机构名称（可选，便于 Free 用户独立使用）
    company: Mapped[str | None] = mapped_column(String(128), nullable=True)
    organization_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id"),
        nullable=True,
    )
    status: Mapped[UserStatus] = mapped_column(String(16), nullable=False, default="active")
    last_login_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
    )

    # === M0 增量字段 (0003 migration 同步) ===
    # 展示信息
    display_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    locale: Mapped[str] = mapped_column(String(16), nullable=False, default="zh-CN")
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Shanghai")
    # 验证时间戳
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    phone_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # 密码 / 锁定
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # 软删除
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deactivation_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Onboarding
    onboarding_role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    onboarding_purposes: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Super admin flag (手工置 true, 禁止 API 修改)
    is_super_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 同意条款
    agreed_terms_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    organization: Mapped[Organization | None] = relationship(lazy="selectin")
    plan: Mapped[UserPlan | None] = relationship(
        back_populates="user", lazy="selectin", uselist=False
    )

    def __repr__(self) -> str:
        return f"<User {self.username} ({self.role})>"


class UserPlan(UUIDPkMixin, TimestampMixin, Base):
    """用户订阅表 T13：记录用户当前套餐与配额。

    - Free：每天 3 次审查（quota_daily=3）
    - Pro：无限审查（quota_daily=-1，不限）
    - Enterprise：团队账号（quota_daily=-1）
    """

    __tablename__ = "user_plans"

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    tier: Mapped[PlanTier] = mapped_column(String(32), nullable=False, default="free")
    status: Mapped[SubscriptionStatus] = mapped_column(
        String(32), nullable=False, default="active"
    )
    # 每日配额上限；-1 表示不限（Pro/Enterprise）
    quota_daily: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    # 当日已用次数（按 UTC 日期重置；DB 兜底版本由 QuotaService 维护）
    used_today: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quota_reset_date: Mapped[str | None] = mapped_column(String(10), nullable=True)  # YYYY-MM-DD
    # 订阅周期（天）
    period_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(nullable=True)

    user: Mapped[User] = relationship(back_populates="plan")

    def __repr__(self) -> str:
        return (
            f"<UserPlan {self.user_id} tier={self.tier} "
            f"used={self.used_today}/{self.quota_daily}>"
        )


class Order(UUIDPkMixin, TimestampMixin, Base):
    """订单表 T14：记录套餐升级/续费订单。"""

    __tablename__ = "orders"

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    plan_tier: Mapped[PlanTier] = mapped_column(String(32), nullable=False)
    amount_cny: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    period_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    status: Mapped[PaymentStatus] = mapped_column(
        String(32), nullable=False, default="pending"
    )
    # 第三方支付流水号（预留）
    payment_channel: Mapped[str | None] = mapped_column(String(32), nullable=True)
    payment_no: Mapped[str | None] = mapped_column(String(128), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(nullable=True)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)

    user: Mapped[User] = relationship(lazy="selectin")

    def __repr__(self) -> str:
        return f"<Order {self.id} user={self.user_id} {self.plan_tier} {self.amount_cny}CNY>"


class Payment(UUIDPkMixin, TimestampMixin, Base):
    """支付流水表 T15：记录每一次支付请求与回调。

    与 Order 一对多（支持同一订单多次重试支付）。
    """

    __tablename__ = "payments"

    order_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    amount_cny: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(
        String(32), nullable=False, default="pending"
    )
    channel: Mapped[str | None] = mapped_column(String(32), nullable=True)
    channel_trade_no: Mapped[str | None] = mapped_column(String(128), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(nullable=True)
    raw_callback: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    note: Mapped[str | None] = mapped_column(String(512), nullable=True)

    def __repr__(self) -> str:
        return f"<Payment {self.id} order={self.order_id} {self.status}>"
