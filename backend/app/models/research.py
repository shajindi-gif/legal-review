"""法律研究 ORM 模型（research_sessions）。

PHASE 1-3：结构化法律研究回答的持久化。answer_json 采用固定段落模板
（【问题】【适用法域及时间】【结论】【法律依据】【分析】【适用条件与例外】
【风险及待核实事项】【官方来源】），citations 保存逐条引证核验结果。
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Date, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import ResearchStatus
from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPkMixin

if TYPE_CHECKING:
    from app.models.workspace import Project


class ResearchSession(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, Base):
    """法律研究会话表。"""

    __tablename__ = "research_sessions"

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True, index=True,
    )
    created_by: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    jurisdiction: Mapped[str] = mapped_column(
        String(64), nullable=False, default="中国大陆"
    )
    as_of_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # 结构化回答（段落模板 → 文本），含每题「结论 / 法律依据 / 分析 ...」
    answer_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # 逐条引证核验结果（CitationVerificationResult 序列化）
    citations: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[ResearchStatus] = mapped_column(
        String(16), nullable=False, default=ResearchStatus.DRAFT
    )
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )

    project: Mapped[Project | None] = relationship(back_populates="research_sessions")

    def __repr__(self) -> str:
        return f"<ResearchSession {self.question[:24]!r} [{self.status}]>"
