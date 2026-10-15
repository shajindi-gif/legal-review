"""analytics_events table for user behavior tracking

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-15

商业化埋点最小集：新建 analytics_events 表 + 两个查询索引
(event, created_at) 用于漏斗/事件趋势查询，(user_id, created_at) 用于按用户回溯。
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers
revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "analytics_events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("anonymous_id", sa.String(64), nullable=True),
        sa.Column("session_id", sa.String(64), nullable=True),
        sa.Column("event", sa.String(64), nullable=False),
        sa.Column(
            "properties", postgresql.JSONB(), nullable=False, server_default="{}"
        ),
        sa.Column("page", sa.String(128), nullable=True),
        sa.Column("referrer", sa.String(256), nullable=True),
        sa.Column("ua", sa.String(256), nullable=True),
        sa.Column("ip_hash", sa.String(64), nullable=True),
    )
    op.create_index(
        "ix_analytics_events_event_created_at",
        "analytics_events",
        ["event", "created_at"],
    )
    op.create_index(
        "ix_analytics_events_user_id_created_at",
        "analytics_events",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_analytics_events_user_id_created_at", table_name="analytics_events"
    )
    op.drop_index(
        "ix_analytics_events_event_created_at", table_name="analytics_events"
    )
    op.drop_table("analytics_events")
