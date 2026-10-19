"""法律研究（Legal Research）测试 - PHASE 1-3。

策略：
- 纯函数（段落组装 / 引证抽取）直接单测。
- 编排层（LegalResearchService）注入假 RAG + 真 CitationVerifier（假法规库）+ Mock LLM。
- API 层用 dependency_overrides 注入假 service / user / db。
"""

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_current_user, get_db
from app.api.v1.research import get_research_service
from app.api.v1.research import router as research_router
from app.core.constants import ResearchStatus
from app.core.errors import AgentError
from app.schemas.legal import RAGSearchResultItem
from app.schemas.research import (
    RESEARCH_SECTION_KEYS,
    ResearchCitation,
    ResearchRequest,
    ResearchSection,
    ResearchSessionRead,
)
from app.services.citation_verifier import (
    CitationVerifier,
    ClauseRecord,
    LawRecord,
)
from app.services.core_auth_client import CorePrincipal
from app.services.legal_research import (
    LegalResearchService,
    _assemble_sections,
    _extract_claims,
)
from app.tools.llm import MockProvider


# ============== 假依赖 ==============
class _FakeLookup:
    """假法规库：民法典 + 第十二条（原文与 Mock LLM 引证一致）。"""

    _LAW_NAME = "中华人民共和国民法典"
    _QUOTED = "十周岁以上的未成年人为限制民事行为能力人。"

    def __init__(self) -> None:
        self._law = LawRecord(
            id=uuid4(),
            law_name=self._LAW_NAME,
            law_type="law",
            law_level="national",
            status="effective",
            effective_date=date(2021, 1, 1),
            expire_date=None,
            source_url="https://flk.npc.gov.cn/detail2.html?ZmY4MDgx",
            source_type="official_db",
        )

    async def find_laws(self, name: str) -> list[LawRecord]:
        if name in self._law.law_name or self._law.law_name in name:
            return [self._law]
        return []

    async def find_clause(self, law_id: UUID, article_no: str | None) -> ClauseRecord | None:
        if law_id != self._law.id or article_no is None:
            return None
        return ClauseRecord(article_no="第十二条", content=self._QUOTED)


class _FakeSession:
    """最小 DB session 桩：add 同步、flush 异步。"""

    def __init__(self) -> None:
        self.added: list[Any] = []

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        return None


def _fake_rag(items: list[RAGSearchResultItem] | None = None) -> MagicMock:
    rag = MagicMock()
    rag.search_simple = AsyncMock(return_value=items or [])
    return rag


def _hit() -> RAGSearchResultItem:
    return RAGSearchResultItem(
        clause_id=uuid4(),
        law_id=uuid4(),
        law_name="中华人民共和国民法典",
        law_type="law",
        law_level="national",
        law_status="effective",
        publish_date=date(2021, 1, 1),
        chapter="总则",
        section=None,
        article_no="第十二条",
        article_title=None,
        content="十周岁以上的未成年人为限制民事行为能力人。",
        keywords=["民事行为能力"],
        vector_score=0.9,
        keyword_score=0.6,
        final_score=0.8,
    )


def _user() -> CorePrincipal:
    return CorePrincipal(
        id=uuid4(),
        tenant_id=None,
        email="u@example.com",
        full_name="测试用户",
        role="submitter",
        is_active=True,
        organization_id=uuid4(),
    )


def _service(
    session: _FakeSession | None = None,
    *,
    rag: MagicMock | None = None,
) -> LegalResearchService:
    return LegalResearchService(
        session or _FakeSession(),  # type: ignore[arg-type]
        rag=rag or _fake_rag(),
        verifier=CitationVerifier(_FakeLookup()),
    )


# ============== 纯函数 ==============
def test_assemble_sections_fixed_order_and_placeholder() -> None:
    req = ResearchRequest(question="未成年人签约是否有效？", jurisdiction="中国大陆")
    raw = {"conclusion": "需视情形而定。"}
    sections = _assemble_sections(req, raw)
    assert [s.key for s in sections] == list(RESEARCH_SECTION_KEYS)
    assert len(sections) == 8
    by_key = {s.key: s for s in sections}
    assert by_key["question"].content == req.question
    assert "现行有效" in by_key["jurisdiction_time"].content
    assert by_key["conclusion"].content == "需视情形而定。"
    # 缺失段以占位文本呈现，不省略段落
    assert by_key["analysis"].content


def test_assemble_sections_uses_as_of_date() -> None:
    req = ResearchRequest(
        question="某问题", jurisdiction="上海市", as_of_date=date(2024, 6, 1)
    )
    sections = _assemble_sections(req, {})
    jt = {s.key: s for s in sections}["jurisdiction_time"]
    assert "2024-06-01" in jt.content
    assert "上海市" in jt.content


def test_extract_claims_skips_invalid_entries() -> None:
    raw = {
        "citations": [
            {"law_name": "民法典", "article_no": "第十二条", "quoted_text": "x"},
            {"law_name": "", "article_no": "第一条"},
            "not-a-dict",
        ]
    }
    claims = _extract_claims(raw)
    assert len(claims) == 1
    assert claims[0].law_name == "民法典"


def test_extract_claims_returns_empty_when_absent() -> None:
    assert _extract_claims({}) == []


# ============== 编排层 ==============
@pytest.mark.asyncio
async def test_create_session_verified_citation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.legal_research.get_llm_provider", lambda: MockProvider()
    )
    session = _FakeSession()
    svc = _service(session, rag=_fake_rag([_hit()]))

    result = await svc.create_session(ResearchRequest(question="未成年人签约效力？"), user=_user())

    assert result.status == ResearchStatus.COMPLETED.value
    assert len(result.sections) == 8
    assert len(result.citations) == 1
    assert result.citations[0].verified is True
    # 引证可点击跳转官方来源
    assert result.citations[0].source_url is not None
    # 已落库
    assert len(session.added) == 1
    assert session.added[0].status == "completed"


@pytest.mark.asyncio
async def test_create_session_rag_failure_degrades(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.legal_research.get_llm_provider", lambda: MockProvider()
    )
    rag = MagicMock()
    rag.search_simple = AsyncMock(side_effect=AgentError("legal_retrieve", "boom"))
    svc = _service(_FakeSession(), rag=rag)

    result = await svc.create_session(ResearchRequest(question="测试问题？"), user=_user())

    # RAG 失败不阻塞：仍产出结构化回答
    assert result.status == ResearchStatus.COMPLETED.value
    assert len(result.sections) == 8


@pytest.mark.asyncio
async def test_create_session_llm_failure_marks_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    class _BrokenProvider:
        async def complete_json(self, *a: Any, **k: Any) -> dict[str, Any]:
            raise AgentError("llm", "no api key")

    monkeypatch.setattr(
        "app.services.legal_research.get_llm_provider", lambda: _BrokenProvider()
    )
    session = _FakeSession()
    svc = _service(session, rag=_fake_rag([_hit()]))

    result = await svc.create_session(ResearchRequest(question="测试问题？"), user=_user())

    assert result.status == ResearchStatus.FAILED.value
    assert len(result.sections) == 8
    assert result.citations == []
    # 失败会话仍落库（可追溯）
    assert len(session.added) == 1


# ============== API 层 ==============
def _make_api_app(service: Any, user: CorePrincipal | None = None) -> FastAPI:
    app = FastAPI()
    app.include_router(research_router)
    app.dependency_overrides[get_research_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: user or _user()

    async def _get_db_override() -> Any:
        yield MagicMock()

    app.dependency_overrides[get_db] = _get_db_override
    return app


def _read(session_id: UUID) -> ResearchSessionRead:
    from datetime import UTC, datetime

    return ResearchSessionRead(
        id=session_id,
        question="未成年人签约效力？",
        jurisdiction="中国大陆",
        as_of_date=None,
        project_id=None,
        status="completed",
        sections=[
            ResearchSection(key="conclusion", title="结论", content="需视情形而定。")
        ],
        citations=[
            ResearchCitation(
                law_name="民法典",
                article_no="第十二条",
                status="verified",
                verified=True,
                source_url="https://flk.npc.gov.cn/x",
            )
        ],
        created_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_api_create_research_returns_201() -> None:
    session_id = uuid4()
    svc = MagicMock()
    svc.create_session = AsyncMock(return_value=_read(session_id))
    app = _make_api_app(svc)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.post(
            "/research/sessions",
            json={"question": "未成年人签约效力？", "top_k": 5},
        )

    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "completed"
    assert body["citations"][0]["source_url"].startswith("https://")
    call_req: ResearchRequest = svc.create_session.await_args.args[0]
    assert call_req.top_k == 5


@pytest.mark.asyncio
async def test_api_list_research_returns_200() -> None:
    from app.schemas.research import ResearchSessionListResponse

    svc = MagicMock()
    svc.list_sessions = AsyncMock(
        return_value=ResearchSessionListResponse(total=0, items=[])
    )
    app = _make_api_app(svc)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.get("/research/sessions")

    assert resp.status_code == 200
    assert resp.json()["total"] == 0


@pytest.mark.asyncio
async def test_api_get_research_not_found_returns_404() -> None:
    from app.main import create_app

    svc = MagicMock()
    svc.get_session = AsyncMock(return_value=None)
    app = create_app()
    app.dependency_overrides[get_research_service] = lambda: svc
    app.dependency_overrides[get_current_user] = lambda: _user()

    async def _get_db_override() -> Any:
        yield MagicMock()

    app.dependency_overrides[get_db] = _get_db_override

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.get(f"/api/v1/research/sessions/{uuid4()}")

    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"
