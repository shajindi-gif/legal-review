"""PHASE 1-2 数据模型扩展（统一工作台 / 法律研究 / 合同审查 / 权威数据源）

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-19

新增：
- projects：统一工作台一级容器
- document_versions：项目下的版本化文档（含解析纯文本、content_hash）
- document_chunks：文档分块 + 向量索引
- research_sessions：法律研究结构化回答 + 引证核验结果
- contract_reviews：合同审查风险分级 + 对照修改视图
- legal_sources：权威数据源合规登记（robots/条款/授权状态）
- legal_documents：补 source_url / source_type / content_hash /
  last_verified_at / document_number 溯源字段

全部可回滚（downgrade 完整逆操作）。
"""
from __future__ import annotations

from collections.abc import Sequence

import pgvector.sqlalchemy.vector as pgv
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONB = postgresql.JSONB(astext_type=sa.Text())
UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    # ---- legal_sources：权威数据源登记 ----
    op.create_table(
        "legal_sources",
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("base_url", sa.String(512), nullable=True),
        sa.Column("domain", sa.String(128), nullable=True),
        sa.Column("robots_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("terms_url", sa.String(512), nullable=True),
        sa.Column("authorization_status", sa.String(16), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("metadata", JSONB, nullable=False, server_default="{}"),
        sa.Column("id", UUID, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_legal_sources_domain", "legal_sources", ["domain"])

    # ---- projects：统一工作台容器 ----
    op.create_table(
        "projects",
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("project_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_by", UUID, nullable=False),
        sa.Column("metadata", JSONB, nullable=False, server_default="{}"),
        sa.Column("id", UUID, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_projects_organization_id", "projects", ["organization_id"])

    # ---- research_sessions：法律研究 ----
    op.create_table(
        "research_sessions",
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("project_id", UUID, nullable=True),
        sa.Column("created_by", UUID, nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("jurisdiction", sa.String(64), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=True),
        sa.Column("answer_json", JSONB, nullable=True),
        sa.Column("citations", JSONB, nullable=False, server_default="[]"),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("metadata", JSONB, nullable=False, server_default="{}"),
        sa.Column("id", UUID, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_research_sessions_organization_id", "research_sessions", ["organization_id"]
    )
    op.create_index(
        "ix_research_sessions_project_id", "research_sessions", ["project_id"]
    )

    # ---- document_versions：版本化文档 ----
    op.create_table(
        "document_versions",
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("project_id", UUID, nullable=True),
        sa.Column("document_id", UUID, nullable=True),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(128), nullable=True),
        sa.Column("file_size", sa.BigInteger(), nullable=True),
        sa.Column("storage_path", sa.String(512), nullable=True),
        sa.Column("content_text", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("parse_status", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_by", UUID, nullable=False),
        sa.Column("metadata", JSONB, nullable=False, server_default="{}"),
        sa.Column("id", UUID, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_id", "version_no", name="uq_document_versions_document_version"
        ),
    )
    op.create_index(
        "ix_document_versions_organization_id", "document_versions", ["organization_id"]
    )
    op.create_index("ix_document_versions_project_id", "document_versions", ["project_id"])
    op.create_index("ix_document_versions_document_id", "document_versions", ["document_id"])

    # ---- contract_reviews：合同审查 ----
    op.create_table(
        "contract_reviews",
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("project_id", UUID, nullable=True),
        sa.Column("document_version_id", UUID, nullable=True),
        sa.Column("created_by", UUID, nullable=False),
        sa.Column("contract_type", sa.String(128), nullable=True),
        sa.Column("stance", sa.String(16), nullable=False),
        sa.Column("overall_risk", sa.String(16), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("findings", JSONB, nullable=False, server_default="[]"),
        sa.Column("redline", JSONB, nullable=False, server_default="[]"),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("metadata", JSONB, nullable=False, server_default="{}"),
        sa.Column("id", UUID, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["document_version_id"], ["document_versions.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_contract_reviews_organization_id", "contract_reviews", ["organization_id"]
    )
    op.create_index("ix_contract_reviews_project_id", "contract_reviews", ["project_id"])
    op.create_index(
        "ix_contract_reviews_document_version_id",
        "contract_reviews",
        ["document_version_id"],
    )

    # ---- document_chunks：分块 + 向量 ----
    op.create_table(
        "document_chunks",
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("document_version_id", UUID, nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("embedding", pgv.VECTOR(dim=1024), nullable=True),
        sa.Column("metadata", JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("id", UUID, nullable=False),
        sa.ForeignKeyConstraint(
            ["document_version_id"], ["document_versions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_version_id", "chunk_index", name="uq_document_chunks_version_index"
        ),
    )
    op.create_index(
        "ix_document_chunks_organization_id", "document_chunks", ["organization_id"]
    )
    op.create_index(
        "ix_document_chunks_document_version_id",
        "document_chunks",
        ["document_version_id"],
    )

    # ---- legal_documents：溯源字段 ----
    op.add_column(
        "legal_documents", sa.Column("source_url", sa.String(512), nullable=True)
    )
    op.add_column(
        "legal_documents", sa.Column("source_type", sa.String(32), nullable=True)
    )
    op.add_column(
        "legal_documents", sa.Column("content_hash", sa.String(64), nullable=True)
    )
    op.add_column(
        "legal_documents",
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "legal_documents", sa.Column("document_number", sa.String(128), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("legal_documents", "document_number")
    op.drop_column("legal_documents", "last_verified_at")
    op.drop_column("legal_documents", "content_hash")
    op.drop_column("legal_documents", "source_type")
    op.drop_column("legal_documents", "source_url")

    op.drop_index("ix_document_chunks_document_version_id", table_name="document_chunks")
    op.drop_index("ix_document_chunks_organization_id", table_name="document_chunks")
    op.drop_table("document_chunks")

    op.drop_index("ix_contract_reviews_document_version_id", table_name="contract_reviews")
    op.drop_index("ix_contract_reviews_project_id", table_name="contract_reviews")
    op.drop_index("ix_contract_reviews_organization_id", table_name="contract_reviews")
    op.drop_table("contract_reviews")

    op.drop_index("ix_document_versions_document_id", table_name="document_versions")
    op.drop_index("ix_document_versions_project_id", table_name="document_versions")
    op.drop_index("ix_document_versions_organization_id", table_name="document_versions")
    op.drop_table("document_versions")

    op.drop_index("ix_research_sessions_project_id", table_name="research_sessions")
    op.drop_index("ix_research_sessions_organization_id", table_name="research_sessions")
    op.drop_table("research_sessions")

    op.drop_index("ix_projects_organization_id", table_name="projects")
    op.drop_table("projects")

    op.drop_index("ix_legal_sources_domain", table_name="legal_sources")
    op.drop_table("legal_sources")
