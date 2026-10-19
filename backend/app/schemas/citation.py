"""法律依据核验（Citation Verification）相关 Schemas。

对应 PHASE 1 的 Citation Verification Engine：
对 AI 生成/用户输入的「法律名称 + 条款编号 + 引用原文」做可核验性判定，
严禁编造；无法核实时必须显式返回「暂未找到可核验的权威依据，需要人工复核」。
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class CitationStatus(StrEnum):
    """单条引用的核验结论。"""

    VERIFIED = "verified"                          # 法规存在 + 条款定位 + 原文吻合 + 时效有效
    LAW_ONLY = "law_only"                          # 法规存在但未定位到条款
    ARTICLE_TEXT_MISMATCH = "article_text_mismatch"  # 条款存在但引用原文与库内不一致
    LAW_NOT_FOUND = "law_not_found"                # 法规名称在库内不存在
    ARTICLE_NOT_FOUND = "article_not_found"        # 法规存在但该条号不存在
    NOT_EFFECTIVE = "not_effective"                # 法规已废止/失效
    NOT_YET_EFFECTIVE = "not_yet_effective"        # 截至适用时间尚未施行
    EXPIRED = "expired"                            # 已过有效期
    INSUFFICIENT = "insufficient"                  # 缺少必要字段，无法核验


# 无法核验时的统一提示（对应指令硬要求）
CANNOT_VERIFY_MESSAGE = "暂未找到可核验的权威依据，需要人工复核。"


class CitationClaim(BaseModel):
    """一条待核验的引用。"""

    law_name: str = Field(..., min_length=1, max_length=255, description="法律/法规名称")
    article_no: str | None = Field(
        default=None, max_length=32, description="条款编号，如「第十二条」"
    )
    quoted_text: str | None = Field(default=None, description="被引用的条文原文（可选）")
    effective_on: date | None = Field(default=None, description="适用时间，默认今天")


class CitationVerificationResult(BaseModel):
    """单条引用的核验结果。"""

    status: CitationStatus
    verified: bool = Field(description="是否完全可核验（名称+条款+原文+时效）")
    needs_human_review: bool
    law_name: str
    article_no: str | None = None
    quoted_text: str | None = None
    matched_law_name: str | None = None
    matched_article_no: str | None = None
    matched_text: str | None = None
    text_similarity: float = Field(default=0.0, ge=0.0, le=1.0)
    validity: str = "unknown"
    source_url: str | None = None
    source_type: str | None = None
    message: str
    checked_at: datetime


class CitationBatchRequest(BaseModel):
    """批量核验请求。"""

    claims: list[CitationClaim] = Field(..., min_length=1, max_length=200)


class CitationBatchResponse(BaseModel):
    """批量核验响应（含汇总统计）。"""

    total: int
    verified: int
    needs_human_review: int
    results: list[CitationVerificationResult]
