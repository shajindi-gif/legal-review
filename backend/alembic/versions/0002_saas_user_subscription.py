"""saas user subscription tables

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-22

Sprint 6 SaaS 用户系统：
- users 表加 company 字段（Free 用户独立使用）
- T13 user_plans：用户订阅与配额（Free/Pro/Enterprise）
- T14 orders：套餐升级/续费订单
- T15 payments：第三方支付流水
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ============== users 加 company 字段 ==============
    op.add_column(
        "users",
        sa.Column("company", sa.String(128), nullable=True),
    )

    # ============== T13 user_plans ==============
    op.create_table(
        "user_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False, unique=True),
        sa.Column("tier", sa.String(32), nullable=False, server_default="free"),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("quota_daily", sa.Integer, nullable=False, server_default="3"),
        sa.Column("used_today", sa.Integer, nullable=False, server_default="0"),
        sa.Column("quota_reset_date", sa.String(10), nullable=True),
        sa.Column("period_days", sa.Integer, nullable=False, server_default="30"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("idx_userplans_tier", "user_plans", ["tier"])
    op.create_index("idx_userplans_status", "user_plans", ["status"])

    # ============== T14 orders ==============
    op.create_table(
        "orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("plan_tier", sa.String(32), nullable=False),
        sa.Column("amount_cny", sa.Numeric(10, 2), nullable=False),
        sa.Column("period_days", sa.Integer, nullable=False, server_default="30"),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("payment_channel", sa.String(32), nullable=True),
        sa.Column("payment_no", sa.String(128), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("idx_orders_user", "orders", ["user_id", "created_at"])
    op.create_index("idx_orders_status", "orders", ["status"])

    # ============== T15 payments ==============
    op.create_table(
        "payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("order_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("orders.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("amount_cny", sa.Numeric(10, 2), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("channel", sa.String(32), nullable=True),
        sa.Column("channel_trade_no", sa.String(128), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_callback", postgresql.JSONB, nullable=True),
        sa.Column("note", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("idx_payments_order", "payments", ["order_id"])
    op.create_index("idx_payments_user", "payments", ["user_id", "created_at"])
    op.create_index("idx_payments_status", "payments", ["status"])


def downgrade() -> None:
    op.drop_table("payments")
    op.drop_table("orders")
    op.drop_table("user_plans")
    op.drop_column("users", "company")
