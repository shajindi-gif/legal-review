"""合同审查服务（Contract Review，PHASE 1-4）。

流程：
1. 解析合同文本（DOCX/PDF/TXT，保真段落，供 Prompt 上下文）
2. 版本化 Prompt（contract_review@v1.0.0）→ LLM 结构化输出
3. 风险分级校验（CRITICAL/HIGH/MEDIUM/LOW/INFO）+ 立场（甲/乙/中立）
4. 生成「对照修改视图」（findings + redline，仅建议视图，不伪装 Word 原生修订）
5. 逐条法律依据走 CitationVerifier 核验（未核实项显式标注，禁止编造）
6. 持久化 ContractReview（可追溯）

设计约束：
- 引证核验为确定性算法，与 LLM 解耦。
- 无风险时 findings/redline 为空数组，不得臆造风险。
- 每次调用记录 prompt 版本与 LLM 用量元数据。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import (
    CONTRACT_RISK_LEVEL_ORDER,
    ContractReviewStatus,
    ContractRiskLevel,
    ReviewStance,
)
from app.core.errors import AppError
from app.core.logging import get_logger
from app.models.contract import ContractReview
from app.schemas.citation import CitationClaim
from app.schemas.contract import (
    EMPTY_SUMMARY,
    STANCE_LABELS,
    ContractCitation,
    ContractFinding,
    ContractRedlineItem,
    ContractReviewListItem,
    ContractReviewListResponse,
    ContractReviewRead,
    ContractReviewRequest,
    highest_risk,
)
from app.services.citation_verifier import CitationVerifier, DbLawLookup
from app.services.core_auth_client import CorePrincipal
from app.services.prompt_manager import get_prompt_manager
from app.services.tenant import apply_org_filter_with_column, load_user_org
from app.tools.llm import get_llm_provider

logger = get_logger("services.contract_review")

_CONTRACT_PROMPT_KEY = "contract_review"
_NO_CONTEXT_NOTE = "（合同全文为空，无法审查。）"
_VALID_LEVELS: set[str] = {str(lv) for lv in CONTRACT_RISK_LEVEL_ORDER}


# ============== 纯函数 ==============
def _format_context(parsed: dict[str, Any]) -> str:
    """把解析后的合同段落格式化为 Prompt 上下文（保真文本 + 段落锚点）。"""
    paragraphs = parsed.get("body_paragraphs") or []
    lines: list[str] = []
    for p in paragraphs:
        if not isinstance(p, dict):
            continue
        text = str(p.get("text") or "").strip()
        if not text:
            continue
        pid = str(p.get("id") or "").strip()
        lines.append(f"[{pid}] {text}" if pid else text)
    return "\n".join(lines) or _NO_CONTEXT_NOTE


def _coerce_level(value: Any) -> str:
    """风险等级归一化：非法值降级为 INFO（不抛出，保证明细完整）。"""
    lv = str(value or "").strip().lower()
    return lv if lv in _VALID_LEVELS else ContractRiskLevel.INFO.value


def _extract_basis(item: dict[str, Any]) -> ContractCitation | None:
    """抽取（可选的）法律依据。缺名为空即视为未提供。"""
    raw = item.get("basis")
    if not isinstance(raw, dict):
        return None
    law_name = str(raw.get("law_name") or "").strip()
    if not law_name:
        return None
    article_no = raw.get("article_no")
    quoted = raw.get("quoted_text")
    return ContractCitation(
        law_name=law_name[:255],
        article_no=str(article_no).strip()[:32] if article_no else None,
        quoted_text=str(quoted) if quoted else None,
    )


def _extract_findings(raw: dict[str, Any]) -> list[ContractFinding]:
    """抽取并归一化风险明细（仅接受结构化 findings 数组）。"""
    items = raw.get("findings")
    findings: list[ContractFinding] = []
    if not isinstance(items, list):
        return findings
    for i, item in enumerate(items, 1):
        if not isinstance(item, dict):
            continue
        issue = str(item.get("issue") or "").strip()
        suggestion = str(item.get("suggestion") or "").strip()
        if not issue and not suggestion:
            continue
        clause_no = item.get("clause_no")
        clause_text = item.get("clause_text")
        findings.append(
            ContractFinding(
                id=f"f{i}",
                level=_coerce_level(item.get("level")),
                clause_no=str(clause_no).strip()[:128] if clause_no else None,
                clause_text=str(clause_text).strip() if clause_text else None,
                issue=issue,
                suggestion=suggestion,
                basis=_extract_basis(item),
            )
        )
    return findings


def _extract_redline(raw: dict[str, Any]) -> list[ContractRedlineItem]:
    """抽取对照修改视图（before → after）。"""
    items = raw.get("redline")
    out: list[ContractRedlineItem] = []
    if not isinstance(items, list):
        return out
    for item in items:
        if not isinstance(item, dict):
            continue
        before = str(item.get("before") or "").strip()
        after = str(item.get("after") or "").strip()
        if not before and not after:
            continue
        clause_no = item.get("clause_no")
        out.append(
            ContractRedlineItem(
                clause_no=str(clause_no).strip()[:128] if clause_no else None,
                before=before,
                after=after,
                reason=str(item.get("reason") or "").strip(),
                level=_coerce_level(item.get("level")),
            )
        )
    return out


def _risk_counts(findings: list[ContractFinding]) -> dict[str, int]:
    """各风险等级计数（固定 5 档顺序）。"""
    counts = {str(lv): 0 for lv in ContractRiskLevel}
    for f in findings:
        key = str(f.level)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _to_read(
    obj: ContractReview,
    findings: list[ContractFinding],
    redline: list[ContractRedlineItem],
) -> ContractReviewRead:
    meta = obj.metadata_ or {}
    original_name = meta.get("original_name")
    return ContractReviewRead(
        id=obj.id,
        contract_type=obj.contract_type,
        stance=str(obj.stance),
        overall_risk=str(obj.overall_risk),
        summary=obj.summary or EMPTY_SUMMARY,
        status=str(obj.status),
        original_name=str(original_name) if original_name else None,
        project_id=obj.project_id,
        findings=findings,
        redline=redline,
        risk_counts=_risk_counts(findings),
        citation_total=sum(1 for f in findings if f.basis is not None),
        citation_verified=sum(1 for f in findings if f.basis_verified),
        created_at=obj.created_at or datetime.now(UTC),
    )


def _to_list_item(obj: ContractReview) -> ContractReviewListItem:
    findings = obj.findings or []
    return ContractReviewListItem(
        id=obj.id,
        contract_type=obj.contract_type,
        stance=str(obj.stance),
        overall_risk=str(obj.overall_risk),
        status=str(obj.status),
        finding_count=len(findings),
        critical_count=sum(
            1 for f in findings if str(f.get("level")) == ContractRiskLevel.CRITICAL.value
        ),
        created_at=obj.created_at or datetime.now(UTC),
    )


# ============== 编排服务 ==============
class ContractReviewService:
    """合同审查编排服务。"""

    def __init__(
        self,
        session: AsyncSession,
        *,
        verifier: CitationVerifier | None = None,
    ) -> None:
        self._session = session
        self._verifier = verifier or CitationVerifier(DbLawLookup(session))

    async def review_text(
        self, req: ContractReviewRequest, *, user: CorePrincipal
    ) -> ContractReviewRead:
        """审查纯文本合同。"""
        parsed: dict[str, Any] = {
            "body_paragraphs": [{"id": "p1", "text": req.text}],
            "parser_version": "inline.v1.0.0",
        }
        return await self._review(
            parsed,
            original_name=None,
            contract_type=req.contract_type,
            stance=req.stance,
            project_id=req.project_id,
            user=user,
        )

    async def review_document(
        self,
        parsed: dict[str, Any],
        *,
        original_name: str | None,
        stance: ReviewStance,
        contract_type: str | None,
        project_id: UUID | None,
        user: CorePrincipal,
    ) -> ContractReviewRead:
        """审查已解析的合同文档（parsers.parse 产出的段落结构）。"""
        return await self._review(
            parsed,
            original_name=original_name,
            contract_type=contract_type,
            stance=stance,
            project_id=project_id,
            user=user,
        )

    async def _review(
        self,
        parsed: dict[str, Any],
        *,
        original_name: str | None,
        contract_type: str | None,
        stance: ReviewStance,
        project_id: UUID | None,
        user: CorePrincipal,
    ) -> ContractReviewRead:
        context = _format_context(parsed)

        # 版本化 Prompt + LLM
        pm = get_prompt_manager()
        spec = pm.get_active(_CONTRACT_PROMPT_KEY)
        provider = get_llm_provider()
        raw: dict[str, Any] = {}
        usage_meta: dict[str, Any] = {}
        status = ContractReviewStatus.DONE
        try:
            prompt = pm.render(
                _CONTRACT_PROMPT_KEY,
                {
                    "contract_type": contract_type or "",
                    "stance": STANCE_LABELS.get(str(stance), "中立"),
                    "context": context,
                },
            )
            raw = await provider.complete_json(
                prompt,
                temperature=spec.temperature,
                max_tokens=8192,
                tier=spec.model_tier,
            )
            usage_meta = raw.get("_usage", {}) if isinstance(raw, dict) else {}
        except AppError as e:
            logger.error(
                "contract_review_llm_failed", error=str(e), original_name=original_name
            )
            status = ContractReviewStatus.FAILED
            raw = {}

        findings = _extract_findings(raw)
        redline = _extract_redline(raw)
        await self._verify_bases(findings)

        overall = highest_risk([str(f.level) for f in findings])
        resolved_type = str(raw.get("contract_type") or "").strip() or contract_type
        summary = str(raw.get("summary") or "").strip() or EMPTY_SUMMARY

        obj = ContractReview(
            id=uuid4(),
            organization_id=user.organization_id,
            project_id=project_id,
            created_by=user.id,
            contract_type=resolved_type,
            stance=stance,
            overall_risk=overall,
            summary=summary,
            findings=[f.model_dump(mode="json") for f in findings],
            redline=[r.model_dump(mode="json") for r in redline],
            status=status,
            metadata_={
                "prompt_key": _CONTRACT_PROMPT_KEY,
                "prompt_version": spec.version,
                "usage": usage_meta,
                "original_name": original_name,
                "parser_version": parsed.get("parser_version"),
            },
        )
        self._session.add(obj)
        await self._session.flush()

        logger.info(
            "contract_review_created",
            review_id=str(obj.id),
            overall_risk=overall,
            findings=len(findings),
            redline=len(redline),
            citations=sum(1 for f in findings if f.basis is not None),
            status=str(status),
            prompt_version=spec.version,
        )
        return _to_read(obj, findings, redline)

    async def _verify_bases(self, findings: list[ContractFinding]) -> None:
        """对每条 risk 的法律依据做核验（就地回填核验字段）。"""
        claims: list[CitationClaim] = []
        targets: list[int] = []
        for idx, f in enumerate(findings):
            if f.basis is None:
                continue
            claims.append(
                CitationClaim(
                    law_name=f.basis.law_name,
                    article_no=f.basis.article_no,
                    quoted_text=f.basis.quoted_text,
                )
            )
            targets.append(idx)
        if not claims:
            return
        results = await self._verifier.verify_many(claims)
        for idx, res in zip(targets, results, strict=True):
            f = findings[idx]
            f.basis_status = str(res.status)
            f.basis_verified = bool(res.verified)
            f.basis_needs_human_review = bool(res.needs_human_review)
            f.basis_message = res.message
            f.basis_source_url = res.source_url

    async def list_reviews(
        self,
        *,
        user: CorePrincipal,
        page: int = 1,
        page_size: int = 20,
    ) -> ContractReviewListResponse:
        """当前租户下的合同审查列表。"""
        org = await load_user_org(self._session, user)
        base = select(ContractReview).where(ContractReview.deleted_at.is_(None))
        base = apply_org_filter_with_column(
            base,
            user,
            org,
            org_column=ContractReview.organization_id,
            user_id_column=ContractReview.created_by,
        )
        total = (
            await self._session.execute(
                select(func.count()).select_from(base.subquery())
            )
        ).scalar_one()

        stmt = (
            base.order_by(ContractReview.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return ContractReviewListResponse(
            total=int(total), items=[_to_list_item(r) for r in rows]
        )

    async def get_review(
        self, review_id: UUID, *, user: CorePrincipal
    ) -> ContractReviewRead | None:
        """按 id 读取合同审查（带租户过滤）。"""
        org = await load_user_org(self._session, user)
        stmt = select(ContractReview).where(ContractReview.id == review_id)
        stmt = apply_org_filter_with_column(
            stmt,
            user,
            org,
            org_column=ContractReview.organization_id,
            user_id_column=ContractReview.created_by,
        )
        obj = (await self._session.execute(stmt)).scalars().first()
        if obj is None:
            return None
        findings = [ContractFinding(**f) for f in (obj.findings or [])]
        redline = [ContractRedlineItem(**r) for r in (obj.redline or [])]
        return _to_read(obj, findings, redline)
