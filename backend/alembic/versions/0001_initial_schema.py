"""initial schema with pgvector

Revision ID: 0001
Revises:
Create Date: 2026-08-22

Sprint 1 → Sprint 2 初始 Schema：
- 扩展：pgvector / uuid-ossp / pg_trgm
- 12 张表（T01~T12）
- HNSW 向量索引（pgvector 0.5+）
- trigram 全文检索
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ============== 扩展 ==============
    op.execute("CREATE EXTENSION IF NOT EXISTS pgvector")
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm')

    # ============== T02 organizations ==============
    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column("region_code", sa.String(12), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_org_parent", "organizations", ["parent_id"],
                    postgresql_where=sa.text("deleted_at IS NULL"))
    op.create_index("idx_org_type", "organizations", ["type"],
                    postgresql_where=sa.text("deleted_at IS NULL"))

    # ============== T01 users ==============
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("username", sa.String(64), nullable=False, unique=True),
        sa.Column("real_name", sa.String(64), nullable=False),
        sa.Column("email", sa.String(128), nullable=True, unique=True),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_users_org", "users", ["organization_id"],
                    postgresql_where=sa.text("deleted_at IS NULL"))
    op.create_index("idx_users_role", "users", ["role"],
                    postgresql_where=sa.text("deleted_at IS NULL"))

    # ============== T05 review_tasks（先于 documents） ==============
    op.create_table(
        "review_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("trace_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("submitter_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("submitter_org_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="created"),
        sa.Column("current_node", sa.String(64), nullable=True),
        sa.Column("iteration", sa.Integer, nullable=False, server_default="0"),
        sa.Column("max_iteration", sa.Integer, nullable=False, server_default="5"),
        sa.Column("priority", sa.String(8), nullable=False, server_default="normal"),
        sa.Column("assigned_reviewer_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_tasks_status", "review_tasks", ["status"],
                    postgresql_where=sa.text("deleted_at IS NULL"))
    op.create_index("idx_tasks_submitter", "review_tasks", ["submitter_id"],
                    postgresql_where=sa.text("deleted_at IS NULL"))
    op.create_index("idx_tasks_reviewer", "review_tasks", ["assigned_reviewer_id"],
                    postgresql_where=sa.text("deleted_at IS NULL"))

    # ============== T03 documents ==============
    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("task_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("review_tasks.id"), nullable=False),
        sa.Column("original_name", sa.String(255), nullable=False),
        sa.Column("file_type", sa.String(16), nullable=False),
        sa.Column("file_size", sa.BigInteger, nullable=False),
        sa.Column("file_hash", sa.String(64), nullable=False),
        sa.Column("storage_path", sa.String(512), nullable=False),
        sa.Column("mime_type", sa.String(64), nullable=True),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("parsed_json", postgresql.JSONB, nullable=True),
        sa.Column("parse_status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_docs_task", "documents", ["task_id"],
                    postgresql_where=sa.text("deleted_at IS NULL"))
    op.create_index("idx_docs_hash", "documents", ["file_hash"],
                    postgresql_where=sa.text("deleted_at IS NULL"))

    # ============== T04 legal_documents ==============
    op.create_table(
        "legal_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("law_name", sa.String(255), nullable=False),
        sa.Column("issuing_authority", sa.String(128), nullable=False),
        sa.Column("publish_date", sa.Date, nullable=False),
        sa.Column("effective_date", sa.Date, nullable=True),
        sa.Column("expire_date", sa.Date, nullable=True),
        sa.Column("law_type", sa.String(32), nullable=False),
        sa.Column("law_level", sa.String(16), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("parent_law_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("legal_documents.id"), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="effective"),
        sa.Column("raw_text", sa.Text, nullable=False),
        sa.Column("parsed_json", postgresql.JSONB, nullable=True),
        sa.Column("keywords", postgresql.ARRAY(sa.String(255)), nullable=False,
                  server_default=sa.text("'{}'::varchar[]")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_law_name", "legal_documents", ["law_name"],
                    postgresql_where=sa.text("deleted_at IS NULL"))
    op.create_index("idx_law_type_level", "legal_documents", ["law_type", "law_level"],
                    postgresql_where=sa.text("deleted_at IS NULL"))
    op.create_index("idx_law_status", "legal_documents", ["status"],
                    postgresql_where=sa.text("deleted_at IS NULL"))

    # ============== T04b legal_clauses（含向量列）==============
    op.create_table(
        "legal_clauses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("law_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("legal_documents.id"), nullable=False),
        sa.Column("chapter", sa.String(128), nullable=True),
        sa.Column("section", sa.String(128), nullable=True),
        sa.Column("article_no", sa.String(32), nullable=False),
        sa.Column("article_title", sa.String(255), nullable=True),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("keywords", postgresql.ARRAY(sa.String(255)), nullable=False,
                  server_default=sa.text("'{}'::varchar[]")),
        sa.Column("embedding", Vector(1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    # HNSW 向量索引（pgvector 0.5+）
    op.execute(
        "CREATE INDEX idx_clause_embedding ON legal_clauses "
        "USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=64)"
    )
    op.create_index("idx_clause_law", "legal_clauses", ["law_id"])
    op.create_index("idx_clause_article", "legal_clauses", ["article_no"])
    # 中文 trigram 全文检索
    op.execute(
        "CREATE INDEX idx_clause_content_trgm ON legal_clauses "
        "USING gin (content gin_trgm_ops)"
    )

    # ============== T06 review_results ==============
    op.create_table(
        "review_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("task_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("review_tasks.id"), nullable=False),
        sa.Column("agent_name", sa.String(64), nullable=False),
        sa.Column("iteration", sa.Integer, nullable=False, server_default="0"),
        sa.Column("node_status", sa.String(16), nullable=False),
        sa.Column("output_json", postgresql.JSONB, nullable=False),
        sa.Column("risks", postgresql.JSONB, nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("evidences", postgresql.JSONB, nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("idx_results_task", "review_results", ["task_id"])
    op.create_index("idx_results_agent", "review_results", ["agent_name", "iteration"])

    # ============== T07 agent_logs ==============
    op.create_table(
        "agent_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("trace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("review_tasks.id"), nullable=True),
        sa.Column("agent_name", sa.String(64), nullable=False),
        sa.Column("iteration", sa.Integer, nullable=False, server_default="0"),
        sa.Column("prompt_version", sa.String(32), nullable=False),
        sa.Column("tool_name", sa.String(64), nullable=True),
        sa.Column("input_summary", sa.Text, nullable=True),
        sa.Column("output_summary", sa.Text, nullable=True),
        sa.Column("tokens_in", sa.Integer, nullable=True),
        sa.Column("tokens_out", sa.Integer, nullable=True),
        sa.Column("latency_ms", sa.Integer, nullable=True),
        sa.Column("cost_cny", sa.Numeric(10, 4), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="success"),
        sa.Column("error_msg", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("idx_logs_trace", "agent_logs", ["trace_id"])
    op.create_index("idx_logs_task", "agent_logs", ["task_id"])
    op.create_index("idx_logs_agent", "agent_logs", ["agent_name", "created_at"])

    # ============== T08 audit_records ==============
    op.create_table(
        "audit_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("trace_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("actor_role", sa.String(32), nullable=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_type", sa.String(32), nullable=True),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("before_value", postgresql.JSONB, nullable=True),
        sa.Column("after_value", postgresql.JSONB, nullable=True),
        sa.Column("ip_address", postgresql.INET, nullable=True),
        sa.Column("user_agent", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("idx_audit_actor", "audit_records", ["actor_id", "created_at"])
    op.create_index("idx_audit_target", "audit_records", ["target_type", "target_id"])
    op.create_index("idx_audit_trace", "audit_records", ["trace_id"])

    # ============== T09 feedback_cases ==============
    op.create_table(
        "feedback_cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("task_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("review_tasks.id"), nullable=False),
        sa.Column("reviewer_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("agent_name", sa.String(64), nullable=False),
        sa.Column("section", sa.String(64), nullable=True),
        sa.Column("ai_output", postgresql.JSONB, nullable=False),
        sa.Column("human_modified", postgresql.JSONB, nullable=False),
        sa.Column("modify_reason", sa.Text, nullable=False),
        sa.Column("reason_category", sa.String(32), nullable=True),
        sa.Column("incorporated", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("prompt_version_after", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("idx_feedback_task", "feedback_cases", ["task_id"])
    op.create_index("idx_feedback_agent", "feedback_cases",
                    ["agent_name", "incorporated"])

    # ============== T10 prompts ==============
    op.create_table(
        "prompts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("prompt_key", sa.String(64), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("template", sa.Text, nullable=False),
        sa.Column("variables", postgresql.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("model_name", sa.String(64), nullable=True),
        sa.Column("temperature", sa.Numeric(3, 2), nullable=False, server_default="0.20"),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("eval_pass_rate", sa.Numeric(5, 2), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("prompt_key", "version", name="uq_prompts_key_version"),
    )
    op.create_index("idx_prompts_key_active", "prompts", ["prompt_key", "status"],
                    postgresql_where=sa.text("status = 'active'"))

    # ============== T11 golden_dataset ==============
    op.create_table(
        "golden_dataset",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("case_name", sa.String(255), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("input_file_path", sa.String(512), nullable=False),
        sa.Column("expected_json", postgresql.JSONB, nullable=False),
        sa.Column("expected_status", sa.String(16), nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("idx_golden_category", "golden_dataset", ["category"])

    # ============== T12 eval_runs ==============
    op.create_table(
        "eval_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("prompt_version", sa.String(32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_cases", sa.Integer, nullable=False),
        sa.Column("parse_acc", sa.Numeric(5, 2), nullable=True),
        sa.Column("retrieval_acc", sa.Numeric(5, 2), nullable=True),
        sa.Column("citation_acc", sa.Numeric(5, 2), nullable=True),
        sa.Column("risk_kappa", sa.Numeric(4, 3), nullable=True),
        sa.Column("report_complete", sa.Numeric(5, 2), nullable=True),
        sa.Column("hallucination_rate", sa.Numeric(5, 2), nullable=True),
        sa.Column("overall_pass", sa.Boolean, nullable=True),
        sa.Column("raw_result_path", sa.String(512), nullable=True),
    )
    op.create_index("idx_evalruns_prompt", "eval_runs", ["prompt_version", "started_at"])


def downgrade() -> None:
    op.drop_table("eval_runs")
    op.drop_table("golden_dataset")
    op.drop_table("prompts")
    op.drop_table("feedback_cases")
    op.drop_table("audit_records")
    op.drop_table("agent_logs")
    op.drop_table("review_results")
    op.drop_index("idx_clause_content_trgm", table_name="legal_clauses")
    op.drop_index("idx_clause_embedding", table_name="legal_clauses")
    op.drop_table("legal_clauses")
    op.drop_table("legal_documents")
    op.drop_table("documents")
    op.drop_table("review_tasks")
    op.drop_table("users")
    op.drop_table("organizations")
