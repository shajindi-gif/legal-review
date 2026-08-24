"""expand documents.mime_type to 128

Revision ID: c369d702b000
Revises: 0002
Create Date: 2026-08-22 23:55:00.000000

只扩展 documents.mime_type 从 VARCHAR(64) 到 VARCHAR(128)。
autogenerate 检测到的其他表 index/timestamp 差异是历史状态不一致，
不在本次修复范围内（不会影响业务功能）。
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c369d702b000"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "documents",
        "mime_type",
        existing_type=sa.VARCHAR(length=64),
        type_=sa.String(length=128),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "documents",
        "mime_type",
        existing_type=sa.String(length=128),
        type_=sa.VARCHAR(length=64),
        existing_nullable=True,
    )
