"""合同审查相关 Pydantic Schemas（PHASE 1-4）。

设计要点：
- 风险分级固定 5 档（CRITICAL/HIGH/MEDIUM/LOW/INFO），排序见 constants。
- 「对照修改视图」= findings（问题清单）+ redline（修改前后对照），仅作为
  建议视图供下载/复制，**不伪装 Word 原生修订**。
- 每条 risk finding 的法律依据（basis）走 CitationVerifier 核验，
  未核实项显式标注，禁止编造。
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.constants import (
    CONTRACT_RISK_LEVEL_ORDER,
    ContractReviewStatus,
    ContractRiskLevel,
    ReviewStance,
)

# 审查立场中文标签（用于 Prompt 与前端展示）
STANCE_LABELS: dict[str, str] = {
    ReviewStance.PARTY_A: "甲方",
    ReviewStance.PARTY_B: "乙方",
    ReviewStance.NEUTRAL: "中立",
}

RISK_LEVEL_LABELS: dict[str, str] = {
    ContractRiskLevel.CRITICAL: "致命",
    ContractRiskLevel.HIGH: "高风险",
    ContractRiskLevel.MEDIUM: "中风险",
    ContractRiskLevel.LOW: "低风险",
    ContractRiskLevel.INFO: "提示",
}

EMPTY_SUMMARY = "（本次审查未产出摘要）"


def highest_risk(levels: list[str]) -> str:
    """返回一组风险等级中的最高等级（最严重）。空集返回 INFO。"""
    valid = [lv for lv in levels if lv in CONTRACT_RISK_LEVEL_ORDER]
    if not valid:
        return ContractRiskLevel.INFO.value
    return min(valid, key=lambda lv: CONTRACT_RISK_LEVEL_ORDER[lv])


class ContractCitation(BaseModel):
    """合同条款引用的法律依据（待核验）。"""

    law_name: str = Field(..., min_length=1, max_length=255)
    article_no: str | None = Field(default=None, max_length=32)
    quoted_text: str | None = None


class ContractFinding(BaseModel):
    """单条风险明细。"""

    id: str
    level: ContractRiskLevel
    clause_no: str | None = None
    clause_text: str | None = None
    issue: str
    suggestion: str
    # 服务端填充的核验结果（LLM 不提供）
    basis: ContractCitation | None = None
    basis_status: str | None = None
    basis_verified: bool = False
    basis_needs_human_review: bool = True
    basis_message: str | None = None
    basis_source_url: str | None = None


class ContractRedlineItem(BaseModel):
    """对照修改视图的一条（before → after）。"""

    clause_no: str | None = None
    before: str
    after: str
    reason: str
    level: ContractRiskLevel


class ContractReviewRequest(BaseModel):
    """合同审查请求（JSON 文本版；文件版走 multipart）。"""

    text: str = Field(..., min_length=10, max_length=500_000, description="合同全文")
    contract_type: str | None = Field(default=None, max_length=128)
    stance: ReviewStance = Field(default=ReviewStance.NEUTRAL)
    project_id: UUID | None = None


class ContractReviewRead(BaseModel):
    """合同审查详情。"""

    id: UUID
    contract_type: str | None
    stance: str
    overall_risk: str
    summary: str
    status: str
    original_name: str | None
    project_id: UUID | None
    findings: list[ContractFinding]
    redline: list[ContractRedlineItem]
    risk_counts: dict[str, int]
    citation_total: int
    citation_verified: int
    created_at: datetime


class ContractReviewListItem(BaseModel):
    """合同审查列表项。"""

    id: UUID
    contract_type: str | None
    stance: str
    overall_risk: str
    status: str
    finding_count: int
    critical_count: int
    created_at: datetime


class ContractReviewListResponse(BaseModel):
    """合同审查列表响应。"""

    total: int
    items: list[ContractReviewListItem]


__all__ = [
    "EMPTY_SUMMARY",
    "RISK_LEVEL_LABELS",
    "STANCE_LABELS",
    "ContractCitation",
    "ContractFinding",
    "ContractRedlineItem",
    "ContractReviewListItem",
    "ContractReviewListResponse",
    "ContractReviewRead",
    "ContractReviewRequest",
    "ContractReviewStatus",
    "ContractRiskLevel",
    "ReviewStance",
    "highest_risk",
]
