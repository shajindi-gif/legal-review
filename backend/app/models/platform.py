"""审计、反馈、Prompt/评测相关 ORM 模型。"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import GoldenCategory, PromptStatus
from app.db.base import Base, TimestampMixin, UUIDPkMixin


class AuditRecord(UUIDPkMixin, Base):
    """审计记录表 T08 - 强制保留 3 年（合规要求）。"""

    __tablename__ = "audit_records"

    trace_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    actor_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    actor_role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    before_value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    after_value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, default=datetime.utcnow
    )


class FeedbackCase(UUIDPkMixin, Base):
    """人工反馈案例表 T09 - 长期保留，作为案例库资产。"""

    __tablename__ = "feedback_cases"

    task_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("review_tasks.id"), nullable=False
    )
    reviewer_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    agent_name: Mapped[str] = mapped_column(String(64), nullable=False)
    section: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ai_output: Mapped[dict] = mapped_column(JSONB, nullable=False)
    human_modified: Mapped[dict] = mapped_column(JSONB, nullable=False)
    modify_reason: Mapped[str] = mapped_column(Text, nullable=False)
    reason_category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    incorporated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    prompt_version_after: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, default=datetime.utcnow
    )


class Prompt(UUIDPkMixin, TimestampMixin, Base):
    """Prompt 版本管理表 T10。"""

    __tablename__ = "prompts"

    prompt_key: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    template: Mapped[str] = mapped_column(Text, nullable=False)
    variables: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    model_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    temperature: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False, default=0.2)
    status: Mapped[PromptStatus] = mapped_column(
        String(16), nullable=False, default="draft"
    )
    eval_pass_rate: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    created_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    activated_at: Mapped[datetime | None] = mapped_column(nullable=True)


class GoldenDataset(UUIDPkMixin, Base):
    """评测集表 T11 - 长期保留。"""

    __tablename__ = "golden_dataset"

    case_name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[GoldenCategory] = mapped_column(String(32), nullable=False)
    input_file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    expected_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    expected_status: Mapped[str] = mapped_column(String(16), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, default=datetime.utcnow
    )


class EvalRun(UUIDPkMixin, Base):
    """评测运行记录表 T12。"""

    __tablename__ = "eval_runs"

    run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, unique=True)
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    total_cases: Mapped[int] = mapped_column(Integer, nullable=False)
    parse_acc: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    retrieval_acc: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    citation_acc: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    risk_kappa: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    report_complete: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    hallucination_rate: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    overall_pass: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    raw_result_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
