"""UI-M11 用户反馈中心 T25 user_feedback 表

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-25 18:00:00.000000

覆盖范围（M11 主题：用户反馈中心）：
- 用户对 AI 输出表达态度/意见（👍/👎/中立 + 可选文字）
- 状态：open / triaged / resolved / wontfix（产品团队后台流转）
- 关联用户、关联目标（report/review/risk/assistant）
- 包含用户主动关闭（closed_at）与管理员回复（admin_reply）

与 T09 feedback_cases 关系：
- T09 面向 prompt 优化（修改前后对比 + modify_reason）
- T25 面向产品反馈（投票 + 评论 + 状态流转）
两者并存，互不干扰。
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_feedback",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("target_kind", sa.String(32), nullable=False),
        sa.Column("target_id", sa.String(64), nullable=False),
        sa.Column("target_label", sa.String(256), nullable=False),
        sa.Column("vote", sa.String(8), nullable=False),
        sa.Column("comment", sa.Text, nullable=True),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default="open",
        ),
        sa.Column("admin_reply", sa.Text, nullable=True),
        sa.Column(
            "context",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_user_feedback_user_created",
        "user_feedback",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_user_feedback_target",
        "user_feedback",
        ["target_kind", "target_id"],
    )
    op.create_index(
        "ix_user_feedback_status",
        "user_feedback",
        ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_user_feedback_status", table_name="user_feedback")
    op.drop_index("ix_user_feedback_target", table_name="user_feedback")
    op.drop_index("ix_user_feedback_user_created", table_name="user_feedback")
    op.drop_table("user_feedback")
