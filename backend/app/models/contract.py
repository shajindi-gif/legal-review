"""合同审查 ORM 模型（contract_reviews）。

PHASE 1-4：合同审查记录的持久化。findings 保存风险分级明细
（CRITICAL/HIGH/MEDIUM/LOW/INFO），redline 保存对照修改视图（不伪装
Word 原生修订，仅作为建议视图供下载/复制）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import (
    ContractReviewStatus,
    ContractRiskLevel,
    ReviewStance,
)
from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPkMixin

if TYPE_CHECKING:
    from app.models.workspace import DocumentVersion, Project


class ContractReview(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, Base):
    """合同审查表。"""

    __tablename__ = "contract_reviews"

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
    document_version_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    created_by: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    # 合同类型（如「房屋租赁合同」「服务合同」），可为空
    contract_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    stance: Mapped[ReviewStance] = mapped_column(
        String(16), nullable=False, default=ReviewStance.NEUTRAL
    )
    overall_risk: Mapped[ContractRiskLevel] = mapped_column(
        String(16), nullable=False, default=ContractRiskLevel.INFO
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 风险明细：[{level, clause_no, clause_text, issue, suggestion, basis}]
    findings: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # 对照修改视图：[{clause_no, before, after, reason, level}]
    redline: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[ContractReviewStatus] = mapped_column(
        String(16), nullable=False, default=ContractReviewStatus.PENDING
    )
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )

    project: Mapped[Project | None] = relationship(back_populates="contract_reviews")
    document_version: Mapped[DocumentVersion | None] = relationship()

    def __repr__(self) -> str:
        return f"<ContractReview {self.contract_type} [{self.overall_risk}]>"
