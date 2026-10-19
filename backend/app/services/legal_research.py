"""法律研究服务（Legal Research，PHASE 1-3）。

流程：
1. RAG 召回相关法规条款（唯一可引用依据）
2. 版本化 Prompt（legal_research@v1.0.0）→ LLM 结构化输出
3. 组装固定 8 段回答模板
4. 逐条引证走 CitationVerifier 核验（未核实项显式标注，禁止编造）
5. 持久化 ResearchSession（可追溯）

设计约束：
- 引证核验为确定性算法，与 LLM 解耦（LLM 只负责分析与表述）。
- 检索为空/不足时，结论必须提示需人工复核，不得臆测。
- 每次调用记录 prompt 版本与 LLM 用量元数据。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.logging import get_logger
from app.models.research import ResearchSession
from app.schemas.citation import CitationClaim
from app.schemas.research import (
    LLM_SECTION_KEYS,
    RESEARCH_SECTION_TITLES,
    SECTION_EMPTY_PLACEHOLDER,
    ResearchCitation,
    ResearchRequest,
    ResearchSection,
    ResearchSessionListItem,
    ResearchSessionListResponse,
    ResearchSessionRead,
)
from app.services.citation_verifier import CitationVerifier, DbLawLookup
from app.services.core_auth_client import CorePrincipal
from app.services.prompt_manager import get_prompt_manager
from app.services.tenant import apply_org_filter_with_column, load_user_org
from app.tools.llm import get_llm_provider
from app.tools.rag import RAGSearchService

logger = get_logger("services.legal_research")

_RESEARCH_PROMPT_KEY = "legal_research"
_NO_RESULT_NOTE = "（法规库未召回可支撑结论的条款，需人工复核。）"


def _format_context(hits: list[Any]) -> str:
    """把 RAG 命中条款格式化为 Prompt 上下文（唯一可引用依据）。"""
    if not hits:
        return _NO_RESULT_NOTE
    lines: list[str] = []
    for idx, h in enumerate(hits, 1):
        title = f" {h.article_title}" if getattr(h, "article_title", None) else ""
        lines.append(
            f"{idx}. 《{h.law_name}》{h.article_no}{title}\n   正文：{h.content}"
        )
    return "\n".join(lines)


def _extract_claims(raw: dict[str, Any]) -> list[CitationClaim]:
    """从 LLM 输出中抽取引证（仅接受结构化 citations 数组）。"""
    claims: list[CitationClaim] = []
    raw_cits = raw.get("citations")
    if not isinstance(raw_cits, list):
        return claims
    for item in raw_cits:
        if not isinstance(item, dict):
            continue
        law_name = str(item.get("law_name") or "").strip()
        if not law_name:
            continue
        article_no = item.get("article_no")
        quoted = item.get("quoted_text")
        claims.append(
            CitationClaim(
                law_name=law_name[:255],
                article_no=str(article_no).strip()[:32] if article_no else None,
                quoted_text=str(quoted) if quoted else None,
            )
        )
    return claims


def _assemble_sections(req: ResearchRequest, raw: dict[str, Any]) -> list[ResearchSection]:
    """按固定 8 段顺序组装回答，缺失段以占位文本呈现（禁止省略段落）。"""
    jurisdiction_time = (
        f"{req.jurisdiction}；效力基准日："
        f"{req.as_of_date.isoformat() if req.as_of_date else '现行有效'}"
    )
    contents: dict[str, str] = {
        "question": req.question,
        "jurisdiction_time": jurisdiction_time,
    }
    for key in LLM_SECTION_KEYS:
        value = raw.get(key)
        text = str(value).strip() if value is not None else ""
        contents[key] = text or SECTION_EMPTY_PLACEHOLDER

    return [
        ResearchSection(
            key=key,
            title=RESEARCH_SECTION_TITLES[key],
            content=contents[key],
        )
        for key in RESEARCH_SECTION_TITLES
    ]


def _to_citation(result: Any) -> ResearchCitation:
    """CitationVerificationResult → ResearchCitation（含可点击 source_url）。"""
    return ResearchCitation(
        law_name=result.law_name,
        article_no=result.article_no,
        quoted_text=result.quoted_text,
        status=str(result.status),
        verified=bool(result.verified),
        needs_human_review=bool(result.needs_human_review),
        matched_law_name=result.matched_law_name,
        matched_article_no=result.matched_article_no,
        source_url=result.source_url,
        validity=result.validity,
        message=result.message,
    )


class LegalResearchService:
    """法律研究编排服务。"""

    def __init__(
        self,
        session: AsyncSession,
        *,
        rag: RAGSearchService | None = None,
        verifier: CitationVerifier | None = None,
    ) -> None:
        self._session = session
        self._rag = rag or RAGSearchService(session)
        self._verifier = verifier or CitationVerifier(DbLawLookup(session))

    async def create_session(
        self, req: ResearchRequest, *, user: CorePrincipal
    ) -> ResearchSessionRead:
        """执行一次法律研究并落库。"""
        # 1. RAG 召回（失败不阻塞：降级为无上下文并提示人工复核）
        hits: list[Any] = []
        try:
            hits = await self._rag.search_simple(req.question, top_k=req.top_k)
        except AppError as e:
            logger.warning("research_rag_failed", error=str(e), question=req.question[:80])
        context = _format_context(hits)

        # 2. 版本化 Prompt + LLM
        pm = get_prompt_manager()
        spec = pm.get_active(_RESEARCH_PROMPT_KEY)
        provider = get_llm_provider()
        raw: dict[str, Any] = {}
        usage_meta: dict[str, Any] = {}
        status = "completed"
        try:
            prompt = pm.render(
                _RESEARCH_PROMPT_KEY,
                {
                    "question": req.question,
                    "jurisdiction": req.jurisdiction,
                    "as_of_date": req.as_of_date.isoformat() if req.as_of_date else "",
                    "context": context,
                },
            )
            raw = await provider.complete_json(
                prompt,
                temperature=spec.temperature,
                max_tokens=4096,
                tier=spec.model_tier,
            )
            usage_meta = raw.get("_usage", {}) if isinstance(raw, dict) else {}
        except AppError as e:
            # 记录失败会话（可追溯），返回降级回答
            logger.error("research_llm_failed", error=str(e), question=req.question[:80])
            status = "failed"
            raw = {
                "risks_to_verify": (
                    f"本次生成失败：{e}。{SECTION_EMPTY_PLACEHOLDER}"
                )
            }

        # 3. 组装 8 段
        sections = _assemble_sections(req, raw)

        # 4. 引证核验
        claims = _extract_claims(raw)
        results = await self._verifier.verify_many(claims) if claims else []
        citations = [_to_citation(r) for r in results]

        # 5. 持久化
        obj = ResearchSession(
            id=uuid4(),
            organization_id=user.organization_id,
            project_id=req.project_id,
            created_by=user.id,
            question=req.question,
            jurisdiction=req.jurisdiction,
            as_of_date=req.as_of_date,
            answer_json={
                "sections": [s.model_dump(mode="json") for s in sections],
                "retrieved": [
                    {
                        "law_name": h.law_name,
                        "article_no": h.article_no,
                        "score": h.final_score,
                    }
                    for h in hits
                ],
                "prompt_version": spec.version,
                "usage": usage_meta,
            },
            citations=[c.model_dump(mode="json") for c in citations],
            status=status,
            metadata_={
                "prompt_key": _RESEARCH_PROMPT_KEY,
                "prompt_version": spec.version,
            },
        )
        self._session.add(obj)
        await self._session.flush()

        logger.info(
            "research_session_created",
            session_id=str(obj.id),
            retrieved=len(hits),
            citations=len(citations),
            verified=sum(1 for c in citations if c.verified),
            status=status,
            prompt_version=spec.version,
        )
        return _to_read(obj, sections, citations)

    async def list_sessions(
        self,
        *,
        user: CorePrincipal,
        page: int = 1,
        page_size: int = 20,
    ) -> ResearchSessionListResponse:
        """当前租户下的研究会话列表。"""
        org = await load_user_org(self._session, user)
        base = select(ResearchSession).where(ResearchSession.deleted_at.is_(None))
        base = apply_org_filter_with_column(
            base,
            user,
            org,
            org_column=ResearchSession.organization_id,
            user_id_column=ResearchSession.created_by,
        )
        total = (
            await self._session.execute(
                select(func.count()).select_from(base.subquery())
            )
        ).scalar_one()

        stmt = (
            base.order_by(ResearchSession.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        items = [_to_list_item(r) for r in rows]
        return ResearchSessionListResponse(total=int(total), items=items)

    async def get_session(
        self, session_id: UUID, *, user: CorePrincipal
    ) -> ResearchSessionRead | None:
        """按 id 读取会话（带租户过滤）。"""
        org = await load_user_org(self._session, user)
        stmt = select(ResearchSession).where(ResearchSession.id == session_id)
        stmt = apply_org_filter_with_column(
            stmt,
            user,
            org,
            org_column=ResearchSession.organization_id,
            user_id_column=ResearchSession.created_by,
        )
        obj = (await self._session.execute(stmt)).scalars().first()
        if obj is None:
            return None
        sections = [ResearchSection(**s) for s in (obj.answer_json or {}).get("sections", [])]
        citations = [ResearchCitation(**c) for c in (obj.citations or [])]
        return _to_read(obj, sections, citations)


def _to_list_item(obj: ResearchSession) -> ResearchSessionListItem:
    citations = obj.citations or []
    return ResearchSessionListItem(
        id=obj.id,
        question=obj.question,
        jurisdiction=obj.jurisdiction,
        status=str(obj.status),
        citation_verified=sum(1 for c in citations if c.get("verified")),
        citation_total=len(citations),
        created_at=obj.created_at,
    )


def _to_read(
    obj: ResearchSession,
    sections: list[ResearchSection],
    citations: list[ResearchCitation],
) -> ResearchSessionRead:
    return ResearchSessionRead(
        id=obj.id,
        question=obj.question,
        jurisdiction=obj.jurisdiction,
        as_of_date=obj.as_of_date,
        project_id=obj.project_id,
        status=str(obj.status),
        sections=sections,
        citations=citations,
        created_at=obj.created_at or datetime.utcnow(),
    )
