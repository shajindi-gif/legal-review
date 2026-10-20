"""规范性文件合法性审核 Schemas（PHASE 1-5）。

对应指令第六条「Government Legal Review」：
- 审核维度 A~J（见 constants.GovReviewDimension）
- 审查输出 10 段标准（GOV_REPORT_SECTION_TITLES）
- 审核结论 4 类（GovReviewConclusion）
- 审核规则包（rule packs，按地域分层）

注意：所有输出均为 **AI 辅助审查结果**，不代表法定审核机构作出的正式结论；
正式合法性审核意见必须经过有权人员审核确认（DISCLAIMER）。
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.constants import (
    GOV_DIMENSION_ORDER,
    GOV_RISK_LEVEL_ORDER,
    GovReviewConclusion,
    GovReviewDimension,
    GovRiskLevel,
    GovRuleReviewStatus,
)

DISCLAIMER = (
    "以上均为 AI 辅助审查结果，不代表法定审核机构作出的正式结论；"
    "正式合法性审核意见必须经过有权人员审核确认。"
)

MISSING_MATERIAL_NOTE = "程序材料尚未提供：仅标记为「材料不足」，不据此认定程序违法。"

# 审查输出 10 段标准（顺序即输出顺序）
GOV_REPORT_SECTION_TITLES: tuple[tuple[str, str], ...] = (
    ("basic_info", "基本信息"),
    ("review_scope", "审核范围"),
    ("review_basis", "审核依据"),
    ("findings", "发现问题"),
    ("clause_locations", "具体条款位置"),
    ("risk_levels", "风险等级"),
    ("suggestions", "修改建议"),
    ("missing_materials", "材料缺失清单"),
    ("pending_human_review", "待人工核实事项"),
    ("opinion_draft", "合法性审核意见初稿"),
)

GOV_REPORT_SECTION_COUNT = len(GOV_REPORT_SECTION_TITLES)


def highest_gov_risk(levels: list[str]) -> str:
    """返回一组风险等级中的最高等级（最严重）。空集返回 INFO。"""
    valid = [lv for lv in levels if lv in GOV_RISK_LEVEL_ORDER]
    if not valid:
        return GovRiskLevel.INFO.value
    return min(valid, key=lambda lv: GOV_RISK_LEVEL_ORDER[lv])


def dimension_sort_key(dimension: str) -> int:
    """维度排序（A→J）。未知维度排到最后。"""
    return GOV_DIMENSION_ORDER.get(dimension, 99)


# ============== 规则包 ==============
class GovRuleRead(BaseModel):
    """单条审核规则。"""

    rule_id: str
    dimension: str
    dimension_label: str
    title: str
    risk_type: str
    severity: str
    law_basis: str
    law_basis_article: str | None = None
    region: str
    effective_date: str | None = None
    condition: str
    evidence_required: list[str] = Field(default_factory=list)
    exception: str | None = None
    source_url: str | None = None
    pending_fields: list[str] = Field(default_factory=list)


class GovRulePackRead(BaseModel):
    """审核规则包（按地域分层）。"""

    pack_id: str
    name: str
    scope: str
    region: str
    description: str
    legal_review_status: str
    reviewed_by: str | None = None
    rule_count: int
    rules: list[GovRuleRead] = Field(default_factory=list)


# ============== 10 段输出标准 ==============
class GovBasicInfo(BaseModel):
    """① 基本信息。"""

    file_name: str | None = None
    issuing_authority: str | None = None
    doc_form: str | None = None
    doc_number: str | None = None
    basis_of_making: str | None = None
    region: str | None = None
    proposed_effective_date: str | None = None
    involved_matters: list[str] = Field(default_factory=list)
    law_citations: list[str] = Field(default_factory=list)
    submitted_materials: list[str] = Field(default_factory=list)


class GovReviewScope(BaseModel):
    """② 审核范围。"""

    region: str | None = None
    pack_ids: list[str] = Field(default_factory=list)
    dimensions: list[str] = Field(default_factory=list)
    dimension_labels: list[str] = Field(default_factory=list)


class GovReviewBasis(BaseModel):
    """③ 审核依据（规则包法律依据 + 文件引用依据）。"""

    rule_basis: list[str] = Field(default_factory=list)
    cited_basis: list[str] = Field(default_factory=list)
    unresolved_basis: list[str] = Field(default_factory=list)


class GovFinding(BaseModel):
    """④ 发现问题（一条风险明细）。"""

    id: str
    dimension: str
    dimension_label: str
    rule_id: str | None = None
    title: str
    risk_type: str
    clause_location: str | None = None
    risk_level: GovRiskLevel
    law_basis: str | None = None
    law_article: str | None = None
    evidence_text: str | None = None
    explanation: str | None = None
    suggestion: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    needs_human_review: bool = True


class GovClauseLocation(BaseModel):
    """⑤ 具体条款位置。"""

    finding_id: str
    dimension: str
    clause_location: str | None = None


class GovRiskLevelSummary(BaseModel):
    """⑥ 风险等级。"""

    level: str
    label: str
    count: int


class GovSuggestion(BaseModel):
    """⑦ 修改建议。"""

    finding_id: str
    dimension: str
    suggestion: str


class GovMissingMaterial(BaseModel):
    """⑧ 材料缺失清单。"""

    material: str
    dimension: str | None = None
    rule_id: str | None = None
    reason: str


class GovPendingItem(BaseModel):
    """⑨ 待人工核实事项。"""

    item: str
    reason: str
    rule_id: str | None = None


class GovReviewReport(BaseModel):
    """审查输出 10 段标准（完整报告）。"""

    task_id: UUID | None = None
    generated_at: datetime
    region: str | None = None
    conclusion: GovReviewConclusion
    conclusion_label: str
    overall_risk: str
    risk_counts: dict[str, int] = Field(default_factory=dict)
    findings_count: int = 0
    pack_ids: list[str] = Field(default_factory=list)
    pack_review_status: dict[str, str] = Field(default_factory=dict)
    disclaimer: str = DISCLAIMER
    # === 10 段 ===
    basic_info: GovBasicInfo
    review_scope: GovReviewScope
    review_basis: GovReviewBasis
    findings: list[GovFinding] = Field(default_factory=list)
    clause_locations: list[GovClauseLocation] = Field(default_factory=list)
    risk_levels: list[GovRiskLevelSummary] = Field(default_factory=list)
    suggestions: list[GovSuggestion] = Field(default_factory=list)
    missing_materials: list[GovMissingMaterial] = Field(default_factory=list)
    pending_human_review: list[GovPendingItem] = Field(default_factory=list)
    opinion_draft: str = ""


__all__ = [
    "DISCLAIMER",
    "GOV_REPORT_SECTION_COUNT",
    "GOV_REPORT_SECTION_TITLES",
    "MISSING_MATERIAL_NOTE",
    "GovBasicInfo",
    "GovClauseLocation",
    "GovFinding",
    "GovMissingMaterial",
    "GovPendingItem",
    "GovReviewBasis",
    "GovReviewConclusion",
    "GovReviewDimension",
    "GovReviewReport",
    "GovReviewScope",
    "GovRiskLevel",
    "GovRiskLevelSummary",
    "GovRulePackRead",
    "GovRuleRead",
    "GovRuleReviewStatus",
    "GovSuggestion",
    "dimension_sort_key",
    "highest_gov_risk",
]
