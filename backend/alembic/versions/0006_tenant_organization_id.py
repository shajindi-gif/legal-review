"""M16.1 tenant scope - 给 6 张业务表加 organization_id 列 + backfill + 索引

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-26

目标: 多租户隔离的 Repository 层支撑 (RLS-style 简化版)。

涉及的表:
- review_tasks      已有 submitter_org_id (冗余保留, 改名为 organization_id 不破坏 FK)
- documents         通过 task_id → review_tasks.organization_id 回填
- review_results    通过 task_id → review_tasks.organization_id 回填
- agent_logs        通过 task_id → review_tasks.organization_id 回填 (task_id 可空)
- notifications     通过 recipient_id → users.organization_id 回填
- user_feedback     通过 user_id → users.organization_id 回填

设计要点:
1. 不引入 PostgreSQL RLS policy (避免 superuser 绕过 + 迁移复杂度)
2. 加 nullable → backfill → NOT NULL 三步走, 兼容老数据
3. 加复合索引 (organization_id, id) 支持 Repository 层 WHERE organization_id = ? 加速
4. legal_documents / legal_clauses 是法规库, 全局共享, 不加列
5. audit_records / prompts / golden_dataset / eval_runs / feedback_cases 是平台数据, 不加列
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers
revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str, None], None] = None
depends_on: Union[str, Sequence[str, None], None] = None


def _add_org_id_column(table_name: str) -> None:
    """给指定表加 organization_id 列 (nullable, 待 backfill 后改 NOT NULL)."""
    op.add_column(
        table_name,
        sa.Column("organization_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )


def _backfill_from_table(
    target_table: str,
    target_column: str,
    source_join_sql: str,
) -> None:
    """用 source_join_sql 描述的 UPDATE 回填 target_table.organization_id.

    例子: source_join_sql = "review_tasks t WHERE t.id = documents.task_id"
    """
    op.execute(
        f"UPDATE {target_table} SET {target_column} = ({source_join_sql}) "
        f"WHERE {target_column} IS NULL"
    )


def _set_not_null(table_name: str, column_name: str) -> None:
    op.alter_column(
        table_name,
        column_name,
        nullable=False,
    )


def _add_fk_and_index(table_name: str) -> None:
    """加 FK 到 organizations(id) + 复合索引 (organization_id, id)."""
    op.create_foreign_key(
        f"fk_{table_name}_organization_id",
        table_name,
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        f"ix_{table_name}_organization",
        table_name,
        ["organization_id", "id"],
    )


def upgrade() -> None:
    # ============================================================
    # 1. review_tasks: 已有 submitter_org_id, 直接改名 + NOT NULL
    # ============================================================
    # 实际不重命名列 (会破坏现有 FK 引用) — 直接加冗余列 organization_id
    # backfill 逻辑: submitter_org_id IS NOT NULL → 直接复制
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    rt_cols = {c["name"] for c in inspector.get_columns("review_tasks")}
    if "organization_id" not in rt_cols:
        _add_org_id_column("review_tasks")
        # 已有 submitter_org_id 必有值 (NOT NULL 约束)
        op.execute(
            "UPDATE review_tasks SET organization_id = submitter_org_id "
            "WHERE organization_id IS NULL"
        )
        _set_not_null("review_tasks", "organization_id")
        _add_fk_and_index("review_tasks")

    # ============================================================
    # 2. documents: 通过 task_id 回填
    # ============================================================
    doc_cols = {c["name"] for c in inspector.get_columns("documents")}
    if "organization_id" not in doc_cols:
        _add_org_id_column("documents")
        _backfill_from_table(
            "documents",
            "organization_id",
            "SELECT t.organization_id FROM review_tasks t WHERE t.id = documents.task_id",
        )
        _set_not_null("documents", "organization_id")
        _add_fk_and_index("documents")

    # ============================================================
    # 3. review_results: 通过 task_id 回填
    # ============================================================
    rr_cols = {c["name"] for c in inspector.get_columns("review_results")}
    if "organization_id" not in rr_cols:
        _add_org_id_column("review_results")
        _backfill_from_table(
            "review_results",
            "organization_id",
            "SELECT t.organization_id FROM review_tasks t WHERE t.id = review_results.task_id",
        )
        _set_not_null("review_results", "organization_id")
        _add_fk_and_index("review_results")

    # ============================================================
    # 4. agent_logs: 通过 task_id 回填 (task_id 可空 → ON DELETE SET NULL)
    # ============================================================
    al_cols = {c["name"] for c in inspector.get_columns("agent_logs")}
    if "organization_id" not in al_cols:
        op.add_column(
            "agent_logs",
            sa.Column(
                "organization_id",
                sa.dialects.postgresql.UUID(as_uuid=True),
                nullable=True,
            ),
        )
        _backfill_from_table(
            "agent_logs",
            "organization_id",
            "SELECT t.organization_id FROM review_tasks t WHERE t.id = agent_logs.task_id",
        )
        # agent_logs.task_id 可空, organization_id 也保持 nullable
        # 单独建索引 (不加 FK, 因为 task_id 没了就断了)
        op.create_index(
            "ix_agent_logs_organization",
            "agent_logs",
            ["organization_id", "id"],
        )

    # ============================================================
    # 5. notifications: 通过 recipient_id → users.organization_id 回填
    # ============================================================
    n_cols = {c["name"] for c in inspector.get_columns("notifications")}
    if "organization_id" not in n_cols:
        _add_org_id_column("notifications")
        _backfill_from_table(
            "notifications",
            "organization_id",
            "SELECT u.organization_id FROM users u WHERE u.id = notifications.recipient_id",
        )
        _set_not_null("notifications", "organization_id")
        _add_fk_and_index("notifications")

    # ============================================================
    # 6. user_feedback: 通过 user_id → users.organization_id 回填
    # ============================================================
    uf_cols = {c["name"] for c in inspector.get_columns("user_feedback")}
    if "organization_id" not in uf_cols:
        _add_org_id_column("user_feedback")
        _backfill_from_table(
            "user_feedback",
            "organization_id",
            "SELECT u.organization_id FROM users u WHERE u.id = user_feedback.user_id",
        )
        _set_not_null("user_feedback", "organization_id")
        _add_fk_and_index("user_feedback")


def downgrade() -> None:
    # 反向: 倒着删
    for table in [
        "user_feedback",
        "notifications",
        "agent_logs",
        "review_results",
        "documents",
        "review_tasks",
    ]:
        bind = op.get_bind()
        inspector = sa.inspect(bind)
        cols = {c["name"] for c in inspector.get_columns(table)}
        if "organization_id" in cols:
            # 先删索引 / FK
            try:
                op.drop_index(f"ix_{table}_organization", table_name=table)
            except Exception:
                pass
            try:
                op.drop_constraint(
                    f"fk_{table}_organization_id", table_name=table, type_="foreignkey"
                )
            except Exception:
                pass
            op.drop_column(table, "organization_id")
