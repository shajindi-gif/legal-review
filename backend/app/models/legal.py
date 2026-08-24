"""法规库 ORM 模型（T04 legal_documents + T04b legal_clauses）。"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import Date, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import get_settings
from app.core.constants import LawLevel, LawStatus, LawType
from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPkMixin


class LegalDocument(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, Base):
    """法规表 T04。"""

    __tablename__ = "legal_documents"

    law_name: Mapped[str] = mapped_column(String(255), nullable=False)
    issuing_authority: Mapped[str] = mapped_column(String(128), nullable=False)
    publish_date: Mapped[date] = mapped_column(Date, nullable=False)
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expire_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    law_type: Mapped[LawType] = mapped_column(String(32), nullable=False)
    law_level: Mapped[LawLevel] = mapped_column(String(16), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    parent_law_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("legal_documents.id"),
        nullable=True,
    )
    status: Mapped[LawStatus] = mapped_column(
        String(16), nullable=False, default="effective"
    )
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    parsed_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    keywords: Mapped[list[str]] = mapped_column(
        ARRAY(String(255)), nullable=False, default=list
    )

    clauses: Mapped[list[LegalClause]] = relationship(
        back_populates="law", cascade="all, delete-orphan", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<LegalDocument {self.law_name} v{self.version}>"


class LegalClause(UUIDPkMixin, Base):
    """法规条款表 T04b - 切分原子化，支持向量检索。"""

    __tablename__ = "legal_clauses"

    law_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("legal_documents.id"), nullable=False
    )
    chapter: Mapped[str | None] = mapped_column(String(128), nullable=True)
    section: Mapped[str | None] = mapped_column(String(128), nullable=True)
    article_no: Mapped[str] = mapped_column(String(32), nullable=False)
    article_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    keywords: Mapped[list[str]] = mapped_column(
        ARRAY(String(255)), nullable=False, default=list
    )
    # BGE-M3 默认 1024 维
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(get_settings().embedding_dim), nullable=True
    )

    law: Mapped[LegalDocument] = relationship(back_populates="clauses")

    def __repr__(self) -> str:
        return f"<LegalClause {self.law.law_name} {self.article_no}>"
