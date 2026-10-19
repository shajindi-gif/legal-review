"""法律研究相关 Pydantic Schemas（PHASE 1-3）。"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.constants import ResearchStatus

# 结构化回答模板：固定 8 段，顺序不可变，缺失段以占位文本呈现（禁止省略段落）
RESEARCH_SECTION_KEYS: tuple[str, ...] = (
    "question",
    "jurisdiction_time",
    "conclusion",
    "legal_basis",
    "analysis",
    "conditions_exceptions",
    "risks_to_verify",
    "official_sources",
)

RESEARCH_SECTION_TITLES: dict[str, str] = {
    "question": "问题",
    "jurisdiction_time": "适用法域及时间",
    "conclusion": "结论",
    "legal_basis": "法律依据",
    "analysis": "分析",
    "conditions_exceptions": "适用条件与例外",
    "risks_to_verify": "风险及待核实事项",
    "official_sources": "官方来源",
}

# LLM 需填充的段落（其余由服务端确定性填充）
LLM_SECTION_KEYS: tuple[str, ...] = (
    "conclusion",
    "legal_basis",
    "analysis",
    "conditions_exceptions",
    "risks_to_verify",
    "official_sources",
)

SECTION_EMPTY_PLACEHOLDER = "（本次回答未提供该部分内容）"


class ResearchRequest(BaseModel):
    """法律研究请求。"""

    question: str = Field(..., min_length=2, max_length=2000, description="法律问题")
    jurisdiction: str = Field(default="中国大陆", max_length=64, description="适用法域")
    as_of_date: date | None = Field(default=None, description="效力基准日（默认现行）")
    project_id: UUID | None = Field(default=None, description="所属项目（可选）")
    top_k: int = Field(default=8, ge=1, le=20, description="RAG 召回条数")


class ResearchSection(BaseModel):
    """结构化回答段落。"""

    key: str
    title: str
    content: str


class ResearchCitation(BaseModel):
    """单条引证（含核验状态 + 官方来源 URL，供前端点击跳转）。"""

    law_name: str
    article_no: str | None = None
    quoted_text: str | None = None
    status: str
    verified: bool
    needs_human_review: bool = False
    matched_law_name: str | None = None
    matched_article_no: str | None = None
    source_url: str | None = None
    validity: str = "unknown"
    message: str | None = None


class ResearchAnswer(BaseModel):
    """结构化回答聚合。"""

    sections: list[ResearchSection]
    citations: list[ResearchCitation]
    citation_verified: int
    citation_total: int


class ResearchSessionRead(BaseModel):
    """研究会话详情。"""

    id: UUID
    question: str
    jurisdiction: str
    as_of_date: date | None
    project_id: UUID | None
    status: str
    sections: list[ResearchSection]
    citations: list[ResearchCitation]
    created_at: datetime


class ResearchSessionListItem(BaseModel):
    """研究会话列表项。"""

    id: UUID
    question: str
    jurisdiction: str
    status: str
    citation_verified: int
    citation_total: int
    created_at: datetime


class ResearchSessionListResponse(BaseModel):
    """研究会话列表响应。"""

    total: int
    items: list[ResearchSessionListItem]


def empty_sections() -> list[ResearchSection]:
    """按固定顺序生成空段落骨架（供前端渲染骨架 / 失败兜底）。"""
    return [
        ResearchSection(
            key=k, title=RESEARCH_SECTION_TITLES[k], content=SECTION_EMPTY_PLACEHOLDER
        )
        for k in RESEARCH_SECTION_KEYS
    ]


__all__ = [
    "LLM_SECTION_KEYS",
    "RESEARCH_SECTION_KEYS",
    "RESEARCH_SECTION_TITLES",
    "SECTION_EMPTY_PLACEHOLDER",
    "ResearchAnswer",
    "ResearchCitation",
    "ResearchRequest",
    "ResearchSection",
    "ResearchSessionListItem",
    "ResearchSessionListResponse",
    "ResearchSessionRead",
    "ResearchStatus",
    "empty_sections",
]
