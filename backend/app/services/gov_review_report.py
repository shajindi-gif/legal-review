"""规范性文件合法性审核报告组装（PHASE 1-5）。

把已有的司法局审查工作流产物（review_results.risks / evidences）与
地域审核规则包，组装为指令要求的标准 **10 段输出**，并给出 4 类结论之一。

设计要点（关键）：
- **确定性**：本服务不调用 LLM，输入确定则输出确定，便于回归测试与追溯。
- **不伪装**：程序材料缺失时只标记「材料不足」，绝不据材料缺失直接认定程序违法。
- **AI 辅助定位**：所有结论均附 DISCLAIMER，正式意见须有权人员审核确认。
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.core.constants import (
    GOV_DIMENSION_LABELS,
    GOV_RISK_LEVEL_LABELS,
    GovReviewConclusion,
    GovRiskLevel,
)
from app.schemas.gov_review import (
    DISCLAIMER,
    MISSING_MATERIAL_NOTE,
    GovBasicInfo,
    GovClauseLocation,
    GovFinding,
    GovMissingMaterial,
    GovPendingItem,
    GovReviewBasis,
    GovReviewReport,
    GovReviewScope,
    GovRiskLevelSummary,
    GovSuggestion,
    dimension_sort_key,
    highest_gov_risk,
)
from app.services.gov_rules import GovRulePack

# RiskItem.dimension（老工作流 5 维）→ 指令 A~J 维度的兜底映射
_BASE_DIMENSION_MAP: dict[str, str] = {
    "authority": "A",
    "procedure": "E",
    "content": "C",
    "prohibition": "C",
    "interest": "D",
}

# 关键词 → A~J 维度（按顺序首次命中即返回）
_KEYWORD_DIMENSION: tuple[tuple[tuple[str, ...], str], ...] = (
    (("主体", "职权", "权限", "制定机关"), "A"),
    (("上位法", "抵触", "相抵触", "冲突"), "B"),
    (("许可", "处罚", "强制", "征收", "收费", "行政权力"), "C"),
    (("义务", "权益", "减损"), "D"),
    (("程序", "公开", "征求意见", "听证", "备案", "审议"), "E"),
    (("公平竞争",), "F"),
    (("营商环境", "市场准入", "地方保护", "歧视"), "G"),
    (("时效", "废止", "失效", "修订", "尚未施行", "有效期"), "H"),
    (("形式", "条款", "编号", "引用", "结构"), "I"),
    (("地方", "区级", "市级", "本区"), "J"),
)

_VALID_DIMENSIONS: set[str] = {str(d) for d in _BASE_DIMENSION_MAP.values()} | {
    "A", "B", "C", "D", "E", "F", "G", "H", "I", "J",
}

_RISK_LEVELS: tuple[str, ...] = (
    GovRiskLevel.CRITICAL,
    GovRiskLevel.HIGH,
    GovRiskLevel.MEDIUM,
    GovRiskLevel.LOW,
    GovRiskLevel.INFO,
)


# ============== 小工具 ==============
def _as_str_list(value: Any) -> list[str]:
    """把任意值规整为去空的字符串列表。"""
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (list, tuple, set)):
        out: list[str] = []
        for item in value:
            text = str(item).strip()
            if text:
                out.append(text)
        return out
    text = str(value).strip()
    return [text] if text else []


def _excerpt(text: Any, limit: int = 240) -> str | None:
    """截断长文本（None → None）。"""
    if text is None:
        return None
    value = str(text).strip()
    if not value:
        return None
    return value[:limit] + ("…" if len(value) > limit else "")


def _coerce_risk_level(value: Any) -> str:
    """把任意 severity 规整为 5 档风险等级之一（未知→ medium）。"""
    text = str(value or "").strip().lower()
    if text in {str(lv) for lv in _RISK_LEVELS}:
        return text
    return GovRiskLevel.MEDIUM.value


def _infer_dimension(risk: dict[str, Any]) -> str:
    """从风险点推断其 A~J 审核维度。"""
    explicit = str(risk.get("dimension_code") or "").strip().upper()
    if explicit in _VALID_DIMENSIONS:
        return explicit

    text = f"{risk.get('risk_type', '')} {risk.get('title', '')}"
    for keywords, dim in _KEYWORD_DIMENSION:
        if any(kw in text for kw in keywords):
            return dim

    return _BASE_DIMENSION_MAP.get(str(risk.get("dimension") or ""), "C")


def _dimension_label(dimension: str) -> str:
    return GOV_DIMENSION_LABELS.get(dimension, dimension)


# ============== ① 基本信息 ==============
def _build_basic_info(
    document: Any, region: str | None
) -> GovBasicInfo:
    parsed = getattr(document, "parsed_json", None)
    if not isinstance(parsed, dict):
        parsed = {}
    return GovBasicInfo(
        file_name=getattr(document, "original_name", None) or parsed.get("file_name"),
        issuing_authority=_excerpt(parsed.get("issuing_authority"), 128),
        doc_form=_excerpt(parsed.get("doc_form") or parsed.get("doc_type"), 64),
        doc_number=_excerpt(parsed.get("doc_number"), 64),
        basis_of_making=_excerpt(
            parsed.get("basis_of_making") or parsed.get("legal_basis"), 240
        ),
        region=region or _excerpt(parsed.get("region"), 64),
        proposed_effective_date=_excerpt(
            parsed.get("proposed_effective_date") or parsed.get("effective_date"), 32
        ),
        involved_matters=_as_str_list(
            parsed.get("involved_matters") or parsed.get("keywords")
        ),
        law_citations=_as_str_list(
            parsed.get("law_citations") or parsed.get("legal_basis_refs")
        ),
        submitted_materials=_as_str_list(parsed.get("submitted_materials")),
    )


# ============== ③ 审核依据 ==============
def _collect_basis(
    results: Iterable[Any], packs: list[GovRulePack]
) -> GovReviewBasis:
    rule_basis: list[str] = []
    for pack in packs:
        for rule in pack.rules:
            if rule.law_basis and rule.law_basis not in rule_basis:
                rule_basis.append(rule.law_basis)

    cited: list[str] = []
    unresolved: list[str] = []
    for result in results:
        for ev in getattr(result, "evidences", None) or []:
            if not isinstance(ev, dict):
                continue
            law_name = str(ev.get("law_name") or "").strip()
            if not law_name:
                continue
            article = str(ev.get("article") or "").strip()
            label = f"《{law_name}》{article}" if article else f"《{law_name}》"
            if label not in cited:
                cited.append(label)
            if not article:
                bare = f"《{law_name}》"
                if bare not in unresolved:
                    unresolved.append(bare)
    return GovReviewBasis(
        rule_basis=rule_basis,
        cited_basis=cited,
        unresolved_basis=unresolved,
    )


# ============== ④ 发现问题 ==============
def _collect_findings(results: Iterable[Any]) -> list[GovFinding]:
    findings: list[GovFinding] = []
    index = 0
    for result in results:
        for raw in getattr(result, "risks", None) or []:
            if not isinstance(raw, dict):
                continue
            ev = raw.get("evidence")
            ev = ev if isinstance(ev, dict) else {}
            index += 1
            dimension = _infer_dimension(raw)
            clause = raw.get("paragraph_id") or raw.get("paragraph_anchor")
            findings.append(
                GovFinding(
                    id=f"g{index}",
                    dimension=dimension,
                    dimension_label=_dimension_label(dimension),
                    title=str(raw.get("risk_type") or "").strip() or "风险点",
                    risk_type=str(raw.get("risk_type") or "").strip(),
                    clause_location=_excerpt(clause, 64),
                    risk_level=_coerce_risk_level(raw.get("severity")),
                    law_basis=_excerpt(ev.get("law_name"), 128),
                    law_article=_excerpt(ev.get("article"), 32),
                    evidence_text=_excerpt(ev.get("original_text")),
                    explanation=_excerpt(ev.get("explanation")),
                    suggestion=str(raw.get("suggestion") or "").strip(),
                    confidence=max(0.0, min(1.0, float(raw.get("confidence") or 0.0))),
                    needs_human_review=True,
                )
            )
    findings.sort(key=lambda f: (dimension_sort_key(f.dimension), f.id))
    return findings


# ============== ⑧ 材料缺失清单 ==============
def _collect_missing_materials(
    packs: list[GovRulePack], provided: list[str]
) -> list[GovMissingMaterial]:
    provided_norm = [p for p in provided if p.strip()]
    missing: list[GovMissingMaterial] = []
    seen: set[str] = set()
    for pack in packs:
        for rule in pack.rules:
            for material in rule.evidence_required:
                if material in seen:
                    continue
                seen.add(material)
                matched = any(
                    material in item or item in material for item in provided_norm
                )
                if matched:
                    continue
                missing.append(
                    GovMissingMaterial(
                        material=material,
                        dimension=rule.dimension,
                        rule_id=rule.rule_id,
                        reason=MISSING_MATERIAL_NOTE,
                    )
                )
    return missing


# ============== 结论 ==============
def _resolve_conclusion(
    findings: list[GovFinding],
    missing: list[GovMissingMaterial],
    overall_status: Any,
) -> GovReviewConclusion:
    if str(overall_status or "") == "fail":
        return GovReviewConclusion.MAJOR_RISK
    if findings:
        top = highest_gov_risk([str(f.risk_level) for f in findings])
        if top in (GovRiskLevel.CRITICAL, GovRiskLevel.HIGH):
            return GovReviewConclusion.MAJOR_RISK
        return GovReviewConclusion.NEEDS_REVISION
    if missing:
        return GovReviewConclusion.INSUFFICIENT_BASIS
    return GovReviewConclusion.NO_OBVIOUS_VIOLATION


# ============== ⑨ 待人工核实事项 ==============
def _collect_pending(
    findings: list[GovFinding],
    missing: list[GovMissingMaterial],
    basis: GovReviewBasis,
    packs: list[GovRulePack],
) -> list[GovPendingItem]:
    items: list[GovPendingItem] = []
    if findings:
        items.append(
            GovPendingItem(
                item=f"共 {len(findings)} 条风险点需人工复核",
                reason="AI 辅助审查结果，须由有权人员核实后确认",
            )
        )
    if basis.unresolved_basis:
        items.append(
            GovPendingItem(
                item="引用依据未标注条号：" + "、".join(basis.unresolved_basis[:5]),
                reason="条号与时效需人工核对后方可引用",
            )
        )
    if missing:
        items.append(
            GovPendingItem(
                item=f"共有 {len(missing)} 项送审材料缺失",
                reason=MISSING_MATERIAL_NOTE,
            )
        )
    for pack in packs:
        if pack.legal_review_status != "reviewed":
            items.append(
                GovPendingItem(
                    item=f"{pack.name} 尚未经法律专业人员审核",
                    reason="地方规则包上线前需法律专业人员审核",
                    rule_id=None,
                )
            )
    return items


# ============== ⑩ 意见初稿 ==============
def _build_opinion_draft(
    *,
    basic: GovBasicInfo,
    findings: list[GovFinding],
    missing: list[GovMissingMaterial],
    conclusion: GovReviewConclusion,
    packs: list[GovRulePack],
) -> str:
    from app.core.constants import GOV_CONCLUSION_LABELS

    lines: list[str] = ["# 规范性文件合法性审核意见（AI 辅助初稿）", ""]
    lines.append("## 一、文件基本情况")
    lines.append(f"- 文件名称：{basic.file_name or '未识别'}")
    lines.append(f"- 制定机关：{basic.issuing_authority or '未识别'}")
    lines.append(f"- 发文形式：{basic.doc_form or '未识别'}")
    lines.append(f"- 文号：{basic.doc_number or '未识别'}")
    lines.append(f"- 适用区域：{basic.region or '未识别'}")
    lines.append("")

    lines.append("## 二、审核范围")
    pack_names = "、".join(p.name for p in packs)
    lines.append("适用规则包：" + (pack_names if pack_names else "无"))
    lines.append("")

    lines.append("## 三、审核结论")
    lines.append(f"**{GOV_CONCLUSION_LABELS.get(conclusion, str(conclusion))}**")
    lines.append("")

    lines.append("## 四、发现问题摘要")
    if findings:
        for f in findings[:20]:
            lines.append(
                f"- [{f.dimension}] {f.title}"
                + (f"（位置：{f.clause_location}）" if f.clause_location else "")
                + f" → 建议：{f.suggestion or '见明细'}"
            )
    else:
        lines.append("- 未发现明显违法问题（以规则包为准，需人工复核）")
    lines.append("")

    lines.append("## 五、材料缺失与待核实事项")
    if missing:
        for m in missing[:20]:
            lines.append(f"- 材料缺失：{m.material}")
    else:
        lines.append("- 送审材料已齐备")
    lines.append("")
    lines.append(f"> {DISCLAIMER}")
    return "\n".join(lines)


# ============== 主入口 ==============
def build_gov_report(
    *,
    results: Iterable[Any],
    packs: list[GovRulePack],
    document: Any = None,
    task: Any = None,
    region: str | None = None,
    generated_at: datetime | None = None,
) -> GovReviewReport:
    """组装指令要求的标准 10 段输出报告。

    Args:
        results: 现有工作流产出的 review_results（含 risks / evidences / output_json）。
        packs: 按地区解析出的规则包集合。
        document: 送审文件（提供 parsed_json / original_name）。
        task: 审查任务（提供 id / title）。
        region: 适用区域（缺省取文件解析结果）。
        generated_at: 生成时间（缺省=当前 UTC，测试可注入）。
    """
    result_list = list(results)
    basic = _build_basic_info(document, region)

    findings = _collect_findings(result_list)
    basis = _collect_basis(result_list, packs)
    missing = _collect_missing_materials(
        packs, basic.submitted_materials
    )
    conclusion = _resolve_conclusion(
        findings, missing, _overall_status(result_list)
    )

    dimensions = sorted(
        {r.dimension for pack in packs for r in pack.rules},
        key=dimension_sort_key,
    )

    risk_counts: dict[str, int] = {str(lv): 0 for lv in _RISK_LEVELS}
    for f in findings:
        risk_counts[str(f.risk_level)] = risk_counts.get(str(f.risk_level), 0) + 1

    risk_levels = [
        GovRiskLevelSummary(
            level=str(lv),
            label=GOV_RISK_LEVEL_LABELS.get(str(lv), str(lv)),
            count=risk_counts.get(str(lv), 0),
        )
        for lv in _RISK_LEVELS
    ]

    task_id = getattr(task, "id", None)
    return GovReviewReport(
        task_id=task_id if isinstance(task_id, UUID) else None,
        generated_at=generated_at or datetime.now(UTC),
        region=basic.region,
        conclusion=conclusion,
        conclusion_label=_conclusion_label(conclusion),
        overall_risk=highest_gov_risk([str(f.risk_level) for f in findings]),
        risk_counts=risk_counts,
        findings_count=len(findings),
        pack_ids=[p.pack_id for p in packs],
        pack_review_status={p.pack_id: p.legal_review_status for p in packs},
        basic_info=basic,
        review_scope=GovReviewScope(
            region=basic.region,
            pack_ids=[p.pack_id for p in packs],
            dimensions=dimensions,
            dimension_labels=[_dimension_label(d) for d in dimensions],
        ),
        review_basis=basis,
        findings=findings,
        clause_locations=[
            GovClauseLocation(
                finding_id=f.id,
                dimension=f.dimension,
                clause_location=f.clause_location,
            )
            for f in findings
        ],
        risk_levels=risk_levels,
        suggestions=[
            GovSuggestion(
                finding_id=f.id, dimension=f.dimension, suggestion=f.suggestion
            )
            for f in findings
        ],
        missing_materials=missing,
        pending_human_review=_collect_pending(findings, missing, basis, packs),
        opinion_draft=_build_opinion_draft(
            basic=basic,
            findings=findings,
            missing=missing,
            conclusion=conclusion,
            packs=packs,
        ),
    )


def _overall_status(results: list[Any]) -> Any:
    """从 review_results 中提取最近一次 risk_assessment 的 overall_status。"""
    status: Any = None
    for result in results:
        output = getattr(result, "output_json", None)
        if isinstance(output, dict) and output.get("overall_status"):
            status = output.get("overall_status")
    return status


def _conclusion_label(conclusion: GovReviewConclusion) -> str:
    from app.core.constants import GOV_CONCLUSION_LABELS

    return GOV_CONCLUSION_LABELS.get(conclusion, str(conclusion))


__all__ = ["build_gov_report"]
