"""UI-M8 通知中心 T24 notifications 表

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-25 14:00:00.000000

覆盖范围（Section 48 + 用户决策）：
- 通知事件源：仅审查节点进度（running / done）
- 推送策略：前端轮询 30s + review 页 SSE 实时增量
- 存储：PG notifications 表（read_at NULL = 未读）

字段：
- recipient_id: 收件人用户
- kind:        通知类型（当前仅 node_progress）
- title/body:  铃铛下拉与列表页直接渲染
- task_id:     关联审查任务（SET NULL 以便任务删除时保留通知历史）
- link:        跳转相对路径（前端拼接）
- payload:     JSONB 节点级上下文（node_name/iteration/severity）
- read_at:     NULL 即未读
- created_at:  服务端 now()
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column(
            "recipient_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(32), nullable=False, server_default="node_progress"),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body", sa.Text, nullable=True),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("review_tasks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("link", sa.String(255), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_notif_recipient_unread",
        "notifications",
        ["recipient_id", "read_at", "created_at"],
    )
    op.create_index(
        "ix_notif_recipient_created",
        "notifications",
        ["recipient_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_notif_recipient_created", table_name="notifications")
    op.drop_index("ix_notif_recipient_unread", table_name="notifications")
    op.drop_table("notifications")
