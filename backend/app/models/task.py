"""审查任务相关 ORM 模型（T05 review_tasks + T06 review_results + T07 agent_logs）。"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import (
    NodeStatus,
    TaskPriority,
    TaskStatus,
)
from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPkMixin

if TYPE_CHECKING:
    from app.models.document import Document


class ReviewTask(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, Base):
    """审查任务表 T05。"""

    __tablename__ = "review_tasks"

    trace_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False, unique=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    submitter_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    submitter_org_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    status: Mapped[TaskStatus] = mapped_column(String(32), nullable=False, default="created")
    current_node: Mapped[str | None] = mapped_column(String(64), nullable=True)
    iteration: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_iteration: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    priority: Mapped[TaskPriority] = mapped_column(
        String(8), nullable=False, default="normal"
    )
    assigned_reviewer_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    submitted_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)

    documents: Mapped[list[Document]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )
    results: Mapped[list[ReviewResult]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )
    logs: Mapped[list[AgentLog]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<ReviewTask {self.trace_id} [{self.status}]>"


class ReviewResult(UUIDPkMixin, Base):
    """审查结果缓存表 T06。"""

    __tablename__ = "review_results"

    task_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("review_tasks.id"), nullable=False
    )
    agent_name: Mapped[str] = mapped_column(String(64), nullable=False)
    iteration: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    node_status: Mapped[NodeStatus] = mapped_column(String(16), nullable=False)
    output_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    risks: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    evidences: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, default=datetime.utcnow
    )

    task: Mapped[ReviewTask] = relationship(back_populates="results")

    def __repr__(self) -> str:
        return f"<ReviewResult {self.agent_name} iter={self.iteration} [{self.node_status}]>"


class AgentLog(UUIDPkMixin, Base):
    """Agent 运行日志表 T07。"""

    __tablename__ = "agent_logs"

    trace_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    task_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("review_tasks.id"), nullable=True
    )
    agent_name: Mapped[str] = mapped_column(String(64), nullable=False)
    iteration: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)
    tool_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    input_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    tokens_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_cny: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="success")
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, default=datetime.utcnow
    )

    task: Mapped[ReviewTask | None] = relationship(back_populates="logs")

    def __repr__(self) -> str:
        return f"<AgentLog {self.agent_name} iter={self.iteration} [{self.status}]>"
