"""法规库相关 Pydantic Schemas。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.constants import LawLevel, LawStatus, LawType


# ============== 法规库 ==============
class LegalDocumentCreate(BaseModel):
    """创建法规请求。"""
    law_name: str = Field(..., min_length=1, max_length=255)
    issuing_authority: str = Field(..., min_length=1, max_length=128)
    publish_date: date
    effective_date: date | None = None
    expire_date: date | None = None
    law_type: LawType
    law_level: LawLevel
    version: str = Field(default="v1.0.0")
    raw_text: str = Field(..., min_length=1)
    keywords: list[str] = Field(default_factory=list)


class LegalDocumentRead(BaseModel):
    """法规查询响应。"""
    id: UUID
    law_name: str
    issuing_authority: str
    publish_date: date
    effective_date: date | None
    expire_date: date | None
    law_type: str
    law_level: str
    version: str
    status: str
    keywords: list[str]
    clause_count: int = 0
    created_at: datetime


class LegalClauseRead(BaseModel):
    """条款查询响应。"""
    id: UUID
    law_id: UUID
    law_name: str = ""
    chapter: str | None
    section: str | None
    article_no: str
    article_title: str | None
    content: str
    keywords: list[str]
    has_embedding: bool = False


class LegalLibraryImportRequest(BaseModel):
    """批量导入请求（POST body）。"""
    documents: list[LegalDocumentCreate]


class LegalLibraryImportResponse(BaseModel):
    """批量导入响应。"""
    total: int
    succeeded: int
    failed: int
    errors: list[dict[str, Any]] = Field(default_factory=list)
    law_ids: list[UUID] = Field(default_factory=list)


# ============== RAG 检索 ==============
class RAGSearchRequest(BaseModel):
    """RAG 检索请求。"""
    query: str = Field(..., min_length=1, max_length=2000, description="审核问题/检索 query")
    top_k: int = Field(default=10, ge=1, le=50)
    # 元数据过滤
    law_types: list[LawType] | None = None
    law_levels: list[LawLevel] | None = None
    law_status: list[LawStatus] | None = Field(default=["effective"])
    # 权重（混合检索）
    vector_weight: float = Field(default=0.7, ge=0.0, le=1.0)
    keyword_weight: float = Field(default=0.3, ge=0.0, le=1.0)


class RAGSearchResultItem(BaseModel):
    """单条检索结果（含证据链字段）。"""
    clause_id: UUID
    law_id: UUID
    law_name: str
    law_type: str
    law_level: str
    law_status: str
    publish_date: date | None
    chapter: str | None
    section: str | None
    article_no: str
    article_title: str | None
    content: str
    keywords: list[str]
    # 分数
    vector_score: float
    keyword_score: float
    final_score: float


class RAGSearchResponse(BaseModel):
    """RAG 检索响应。"""
    query: str
    total: int
    items: list[RAGSearchResultItem]
    took_ms: int


# ============== 法规时效 ==============
class LawTimeValidity(BaseModel):
    """法规时效性检查结果。"""
    law_id: UUID
    law_name: str
    status: str
    is_effective: bool
    expire_date: date | None
    days_to_expire: int | None
    warning: str | None = None
