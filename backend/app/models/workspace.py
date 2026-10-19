"""统一工作台 ORM 模型（projects / document_versions / document_chunks）。

PHASE 1-2：为「项目 → 版本文档 → 分块（含向量）」提供持久化骨架。

约定：新表统一 UUID 主键 + organization_id 多租户隔离 + created_at/updated_at
+ created_by + status。
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import get_settings
from app.core.constants import DocumentVersionStatus, ProjectStatus, ProjectType
from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPkMixin

if TYPE_CHECKING:
    from app.models.contract import ContractReview
    from app.models.research import ResearchSession


class Project(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, Base):
    """项目表：统一工作台的一级容器。"""

    __tablename__ = "projects"

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    project_type: Mapped[ProjectType] = mapped_column(
        String(32), nullable=False, default=ProjectType.LEGAL_RESEARCH
    )
    status: Mapped[ProjectStatus] = mapped_column(
        String(16), nullable=False, default=ProjectStatus.ACTIVE
    )
    created_by: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )

    versions: Mapped[list[DocumentVersion]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    research_sessions: Mapped[list[ResearchSession]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    contract_reviews: Mapped[list[ContractReview]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Project {self.name} [{self.project_type}]>"


class DocumentVersion(UUIDPkMixin, TimestampMixin, Base):
    """文档版本表：编辑/解析产物的版本化存储。

    与 ``documents``（送审原始文件）互补：documents 记录上传的原始文件，
    document_versions 记录某一项目下内容随时间的版本演化（含解析后的纯文本）。
    """

    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint(
            "document_id", "version_no", name="uq_document_versions_document_version"
        ),
    )

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
    document_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    storage_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    content_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # sha256（与 documents.file_hash 同规格）
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    parse_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending"
    )
    status: Mapped[DocumentVersionStatus] = mapped_column(
        String(16), nullable=False, default=DocumentVersionStatus.DRAFT
    )
    created_by: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )

    project: Mapped[Project | None] = relationship(back_populates="versions")
    chunks: Mapped[list[DocumentChunk]] = relationship(
        back_populates="document_version", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<DocumentVersion {self.title} v{self.version_no}>"


class DocumentChunk(UUIDPkMixin, Base):
    """文档分块表：解析后按段/条切分的原子块，含向量索引。"""

    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint(
            "document_version_id", "chunk_index",
            name="uq_document_chunks_version_index",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # BGE-M3 默认 1024 维（与 legal_clauses 保持一致）
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(get_settings().embedding_dim), nullable=True
    )
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    document_version: Mapped[DocumentVersion] = relationship(back_populates="chunks")

    def __repr__(self) -> str:
        return f"<DocumentChunk v={self.document_version_id} #{self.chunk_index}>"
