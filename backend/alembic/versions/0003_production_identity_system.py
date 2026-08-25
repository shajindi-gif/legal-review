"""production identity system (users extensions + 6 new tables)

Revision ID: 0003
Revises: c369d702b000
Create Date: 2026-08-25 10:00:00.000000

把 Demo-only 系统升级为生产级 SaaS 身份系统：

users 扩展 13 列:
- display_name / avatar_url / locale / timezone
- email_verified_at / phone_verified_at
- password_changed_at / failed_login_count / locked_until
- deactivated_at / deactivation_reason
- onboarding_role / onboarding_purposes / onboarding_completed_at
- is_super_admin

新增 6 表:
- T16 oauth_identities         OAuth 登录方式绑定
- T17 verification_codes       短信/邮箱验证码
- T18 refresh_tokens           Refresh token 持久化（支持 rotation + revoke）
- T19 user_login_events        登录审计
- T20 user_acquisition_sources UTM 归因
- T21 user_events              通用事件埋点
- T22 account_link_pending     待合并账号队列
- T23 rate_limit_buckets       应用层限流（Redis 备份）

设计文档:
- AUTH_SYSTEM_AUDIT.md
- AUTH_ARCHITECTURE.md
- ACCOUNT_LINKING_DESIGN.md
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "0003"
down_revision: Union[str, None] = "c369d702b000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ============================================================
    # Part A: users 表加 13 列（演示用户与所有历史数据继续保留）
    # ============================================================
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_cols = {c["name"] for c in inspector.get_columns("users")}

    def add_user_col(name: str, col: sa.Column) -> None:
        if name not in existing_cols:
            op.add_column("users", col)

    # 展示信息
    add_user_col("display_name", sa.Column("display_name", sa.String(64), nullable=True))
    add_user_col("avatar_url", sa.Column("avatar_url", sa.Text, nullable=True))
    add_user_col("locale", sa.Column("locale", sa.String(16), nullable=False, server_default="zh-CN"))
    add_user_col("timezone", sa.Column("timezone", sa.String(64), nullable=False, server_default="Asia/Shanghai"))

    # 验证时间戳
    add_user_col("email_verified_at", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
    add_user_col("phone_verified_at", sa.Column("phone_verified_at", sa.DateTime(timezone=True), nullable=True))

    # 密码 / 锁定
    add_user_col("password_changed_at", sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True))
    add_user_col("failed_login_count", sa.Column("failed_login_count", sa.Integer, nullable=False, server_default="0"))
    add_user_col("locked_until", sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True))

    # 软删除
    add_user_col("deactivated_at", sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True))
    add_user_col("deactivation_reason", sa.Column("deactivation_reason", sa.String(64), nullable=True))

    # Onboarding
    add_user_col("onboarding_role", sa.Column("onboarding_role", sa.String(32), nullable=True))
    add_user_col("onboarding_purposes", sa.Column("onboarding_purposes", postgresql.JSONB, nullable=True))
    add_user_col("onboarding_completed_at", sa.Column("onboarding_completed_at", sa.DateTime(timezone=True), nullable=True))

    # Super admin flag（手工置 true，禁止 API 修改）
    add_user_col("is_super_admin", sa.Column("is_super_admin", sa.Boolean, nullable=False, server_default=sa.text("false")))

    # 同意条款
    add_user_col("agreed_terms_at", sa.Column("agreed_terms_at", sa.DateTime(timezone=True), nullable=True))

    # phone 部分唯一索引：去掉 +86 前缀后必须唯一
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_users_phone_normalized
        ON users (regexp_replace(phone, '^[+]?86', ''))
        WHERE phone IS NOT NULL
        """
    )

    # 常用检索索引
    op.create_index("ix_users_phone_verified", "users", ["phone_verified_at"])
    op.create_index("ix_users_email_verified", "users", ["email_verified_at"])
    op.create_index("ix_users_deactivated", "users", ["deactivated_at"])
    op.create_index("ix_users_status", "users", ["status"])

    # ============================================================
    # Part B: T16 oauth_identities
    # ============================================================
    op.create_table(
        "oauth_identities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("provider_user_id", sa.String(128), nullable=False),
        sa.Column("provider_email", sa.String(255), nullable=True),
        sa.Column("provider_email_verified", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("provider_display_name", sa.String(128), nullable=True),
        sa.Column("provider_avatar_url", sa.Text, nullable=True),
        sa.Column("access_token_enc", sa.LargeBinary, nullable=True),
        sa.Column("refresh_token_enc", sa.LargeBinary, nullable=True),
        sa.Column("scope", sa.Text, nullable=True),
        sa.Column("raw_profile", postgresql.JSONB, nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.UniqueConstraint("provider", "provider_user_id", name="uq_oauth_provider_user"),
    )
    op.create_index("ix_oauth_user", "oauth_identities", ["user_id"])
    op.create_index("ix_oauth_provider_email", "oauth_identities", ["provider", "provider_email"])

    # ============================================================
    # Part C: T17 verification_codes
    # ============================================================
    op.create_table(
        "verification_codes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("target", sa.String(64), nullable=False),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("purpose", sa.String(32), nullable=False),
        sa.Column("code_hash", sa.String(128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempt_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer, nullable=False, server_default="5"),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip_address", postgresql.INET, nullable=True),
        sa.Column("user_agent", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_vc_target_purpose", "verification_codes",
                    ["target", "purpose", sa.text("created_at DESC")])
    op.create_index("ix_vc_expires", "verification_codes", ["expires_at"])

    # ============================================================
    # Part D: T18 refresh_tokens
    # ============================================================
    op.create_table(
        "refresh_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("refresh_tokens.id"), nullable=True),
        sa.Column("revoke_reason", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.Text, nullable=True),
        sa.Column("ip_address", postgresql.INET, nullable=True),
        sa.Column("device_id", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_rt_user", "refresh_tokens", ["user_id"])
    op.create_index("ix_rt_expires", "refresh_tokens", ["expires_at"])

    # ============================================================
    # Part E: T19 user_login_events
    # ============================================================
    op.create_table(
        "user_login_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("identifier", sa.String(128), nullable=True),
        sa.Column("login_method", sa.String(32), nullable=False),
        sa.Column("success", sa.Boolean, nullable=False),
        sa.Column("failure_reason", sa.String(64), nullable=True),
        sa.Column("ip_address", postgresql.INET, nullable=True),
        sa.Column("user_agent", sa.Text, nullable=True),
        sa.Column("device_id", sa.String(128), nullable=True),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_login_user_time", "user_login_events",
                    ["user_id", sa.text("created_at DESC")])
    op.create_index("ix_login_ip_time", "user_login_events",
                    ["ip_address", sa.text("created_at DESC")])
    op.create_index("ix_login_method_time", "user_login_events",
                    ["login_method", sa.text("created_at DESC")])

    # ============================================================
    # Part F: T20 user_acquisition_sources
    # ============================================================
    op.create_table(
        "user_acquisition_sources",
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("utm_source", sa.String(64), nullable=True),
        sa.Column("utm_medium", sa.String(64), nullable=True),
        sa.Column("utm_campaign", sa.String(128), nullable=True),
        sa.Column("utm_content", sa.String(128), nullable=True),
        sa.Column("utm_term", sa.String(128), nullable=True),
        sa.Column("referrer", sa.Text, nullable=True),
        sa.Column("landing_page", sa.Text, nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_uas_utm_source", "user_acquisition_sources", ["utm_source"])
    op.create_index("ix_uas_utm_campaign", "user_acquisition_sources", ["utm_campaign"])

    # ============================================================
    # Part G: T21 user_events
    # ============================================================
    op.create_table(
        "user_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("anonymous_id", sa.String(64), nullable=True),
        sa.Column("event_name", sa.String(64), nullable=False),
        sa.Column("properties", postgresql.JSONB, nullable=True),
        sa.Column("ip_address", postgresql.INET, nullable=True),
        sa.Column("user_agent", sa.Text, nullable=True),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_event_name_time", "user_events",
                    ["event_name", sa.text("created_at DESC")])
    op.create_index("ix_event_user_time", "user_events",
                    ["user_id", sa.text("created_at DESC")])
    op.create_index("ix_event_anon_time", "user_events",
                    ["anonymous_id", sa.text("created_at DESC")])

    # ============================================================
    # Part H: T22 account_link_pending
    # ============================================================
    op.create_table(
        "account_link_pending",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("existing_user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("new_provider", sa.String(16), nullable=False),
        sa.Column("new_provider_user_id", sa.String(128), nullable=False),
        sa.Column("new_email", sa.String(255), nullable=True),
        sa.Column("new_email_verified", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("new_raw_profile", postgresql.JSONB, nullable=True),
        sa.Column("state", sa.String(32), nullable=False, server_default="waiting_confirm"),
        sa.Column("confirm_token", postgresql.UUID(as_uuid=True),
                  nullable=False, unique=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip_address", postgresql.INET, nullable=True),
        sa.Column("user_agent", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_alp_user_state", "account_link_pending",
                    ["existing_user_id", "state"])
    op.create_index("ix_alp_expires", "account_link_pending", ["expires_at"])

    # ============================================================
    # Part I: T23 rate_limit_buckets (数据库兜底，Redis 优先)
    # ============================================================
    op.create_table(
        "rate_limit_buckets",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("bucket_key", sa.String(255), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_seconds", sa.Integer, nullable=False),
        sa.Column("count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("max_count", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_rlb_key_window", "rate_limit_buckets",
                    ["bucket_key", "window_started_at"])


def downgrade() -> None:
    # 反向顺序删除
    op.drop_table("rate_limit_buckets")
    op.drop_table("account_link_pending")
    op.drop_table("user_events")
    op.drop_table("user_acquisition_sources")
    op.drop_table("user_login_events")
    op.drop_table("refresh_tokens")
    op.drop_table("verification_codes")
    op.drop_table("oauth_identities")

    # users 索引与列
    op.execute("DROP INDEX IF EXISTS ux_users_phone_normalized")
    op.drop_index("ix_users_status", "users")
    op.drop_index("ix_users_deactivated", "users")
    op.drop_index("ix_users_email_verified", "users")
    op.drop_index("ix_users_phone_verified", "users")

    for col in [
        "agreed_terms_at",
        "is_super_admin",
        "onboarding_completed_at",
        "onboarding_purposes",
        "onboarding_role",
        "deactivation_reason",
        "deactivated_at",
        "locked_until",
        "failed_login_count",
        "password_changed_at",
        "phone_verified_at",
        "email_verified_at",
        "timezone",
        "locale",
        "avatar_url",
        "display_name",
    ]:
        op.drop_column("users", col)
