"""法规库 ORM 模型（T04 legal_documents + T04b legal_clauses）。"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import get_settings
from app.core.constants import (
    LawLevel,
    LawStatus,
    LawType,
    LegalSourceType,
    SourceAuthorizationStatus,
)
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
    # ---- PHASE 1-2: 权威来源溯源字段 ----
    # 权威来源 URL（引证可点击跳转；由 CitationVerifier 读取）
    source_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # 来源类型（official_db / gov_portal / local_gov / ...）
    source_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # 正文内容 sha256（变更检测 / 去重）
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 最近一次与权威来源核验/同步时间
    last_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # 发文字号（如「沪府发〔2024〕3 号」）
    document_number: Mapped[str | None] = mapped_column(String(128), nullable=True)

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


class LegalSource(UUIDPkMixin, TimestampMixin, Base):
    """权威数据源登记表（PHASE 1-2）。

    用于逐源记录 robots.txt / 使用条款 / 授权状态，确保合规访问；
    ``authorization_status`` 未核实前一律 UNKNOWN，禁止宣称 READY。
    """

    __tablename__ = "legal_sources"

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    source_type: Mapped[LegalSourceType] = mapped_column(
        String(32), nullable=False, default=LegalSourceType.MANUAL
    )
    base_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    domain: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    robots_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    terms_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    authorization_status: Mapped[SourceAuthorizationStatus] = mapped_column(
        String(16), nullable=False, default=SourceAuthorizationStatus.UNKNOWN
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )

    def __repr__(self) -> str:
        return f"<LegalSource {self.name} [{self.authorization_status}]>"
