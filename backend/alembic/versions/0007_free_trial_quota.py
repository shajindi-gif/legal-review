"""free-trial quota columns for user_plans

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-14

将 Free 套餐从「每日 3 次」改为「累计 2 次免费体验后收费」：
- user_plans 新增 free_trial_used（累计已用体验次数）
- user_plans 新增 free_trial_limit（免费体验上限，默认 2）
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers
revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_plans",
        sa.Column("free_trial_used", sa.Integer, nullable=False, server_default="0"),
    )
    op.add_column(
        "user_plans",
        sa.Column("free_trial_limit", sa.Integer, nullable=False, server_default="2"),
    )


def downgrade() -> None:
    op.drop_column("user_plans", "free_trial_limit")
    op.drop_column("user_plans", "free_trial_used")