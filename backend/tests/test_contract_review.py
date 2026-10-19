"""合同审查（Contract Review）测试 - PHASE 1-4。

策略：
- 纯函数（段落格式化 / 等级归一化 / findings / redline / 计数）直接单测。
- 编排层（ContractReviewService）注入真 CitationVerifier（假法规库）+ Mock LLM。
- API 层用 dependency_overrides 注入假 service / user / db。
"""

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_current_user, get_db
from app.api.v1.contract import get_contract_service
from app.api.v1.contract import router as contract_router
from app.core.constants import (
    ContractReviewStatus,
    ContractRiskLevel,
    ReviewStance,
)
from app.core.errors import AgentError
from app.schemas.contract import (
    ContractFinding,
    ContractReviewRead,
    ContractReviewRequest,
    highest_risk,
)
from app.services.citation_verifier import CitationVerifier, ClauseRecord, LawRecord
from app.services.contract_review import (
    ContractReviewService,
    _coerce_level,
    _extract_findings,
    _extract_redline,
    _format_context,
    _risk_counts,
)
from app.services.core_auth_client import CorePrincipal
from app.tools.llm import MockProvider


# ============== 假依赖 ==============
class _FakeLookup:
    """假法规库：民法典 + 第十二条（与 Mock LLM 引证一致）。"""

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

    async def find_clause(
        self, law_id: UUID, article_no: str | None
    ) -> ClauseRecord | None:
        if law_id != self._law.id or article_no is None:
            return None
        return ClauseRecord(article_no="第十二条", content=self._QUOTED)


class _FakeSession:
    """最小 DB session 桩。"""

    def __init__(self) -> None:
        self.added: list[Any] = []

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        return None


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


def _service(session: _FakeSession | None = None) -> ContractReviewService:
    return ContractReviewService(
        session or _FakeSession(),  # type: ignore[arg-type]
        verifier=CitationVerifier(_FakeLookup()),
    )


def _parsed() -> dict[str, Any]:
    return {
        "body_paragraphs": [
            {"id": "p1", "text": "甲方应在乙方支付押金后交付房屋。"},
            {"id": "p2", "text": "乙方支付的押金，甲方有权不予退还。"},
        ],
        "parser_version": "docx.v1.0.0",
    }


# ============== 纯函数 ==============
def test_format_context_with_anchors() -> None:
    ctx = _format_context(_parsed())
    assert "[p1]" in ctx
    assert "[p2]" in ctx
    assert "押金" in ctx


def test_format_context_empty() -> None:
    assert "无法审查" in _format_context({"body_paragraphs": []})


def test_coerce_level() -> None:
    assert _coerce_level("HIGH") == ContractRiskLevel.HIGH.value
    assert _coerce_level(" critical ") == ContractRiskLevel.CRITICAL.value
    assert _coerce_level("bogus") == ContractRiskLevel.INFO.value
    assert _coerce_level(None) == ContractRiskLevel.INFO.value


def test_extract_findings_skips_invalid() -> None:
    raw = {
        "findings": [
            {"level": "high", "issue": "问题", "suggestion": "建议"},
            {"level": "high"},  # 无 issue/suggestion → 跳过
            "not-a-dict",
            {"level": "bogus", "issue": "x", "suggestion": "y", "basis": {"law_name": ""}},
        ]
    }
    findings = _extract_findings(raw)
    assert len(findings) == 2
    assert findings[0].id == "f1"
    assert findings[0].level == ContractRiskLevel.HIGH
    assert findings[1].level == ContractRiskLevel.INFO
    assert findings[1].basis is None  # 空 law_name → 视为未提供


def test_extract_redline() -> None:
    raw = {
        "redline": [
            {"clause_no": "第3条", "before": "a", "after": "b", "reason": "r", "level": "high"},
            {"clause_no": None, "before": "", "after": ""},  # 空 → 跳过
        ]
    }
    items = _extract_redline(raw)
    assert len(items) == 1
    assert items[0].before == "a" and items[0].after == "b"


def test_highest_risk_and_counts() -> None:
    assert highest_risk(["low", "critical", "medium"]) == ContractRiskLevel.CRITICAL.value
    assert highest_risk([]) == ContractRiskLevel.INFO.value
    findings = [
        ContractFinding(id="f1", level=ContractRiskLevel.HIGH, issue="a", suggestion="b"),
        ContractFinding(id="f2", level=ContractRiskLevel.INFO, issue="c", suggestion="d"),
    ]
    counts = _risk_counts(findings)
    assert counts[ContractRiskLevel.HIGH.value] == 1
    assert counts[ContractRiskLevel.INFO.value] == 1
    assert counts[ContractRiskLevel.CRITICAL.value] == 0


# ============== 编排层 ==============
@pytest.mark.asyncio
async def test_review_document_end_to_end(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.contract_review.get_llm_provider", lambda: MockProvider()
    )
    session = _FakeSession()
    svc = _service(session)

    result = await svc.review_document(
        _parsed(),
        original_name="lease.docx",
        stance=ReviewStance.PARTY_B,
        contract_type=None,
        project_id=None,
        user=_user(),
    )

    assert result.status == ContractReviewStatus.DONE.value
    assert result.stance == ReviewStance.PARTY_B.value
    assert len(result.findings) == 2
    # overall 取最高等级
    assert result.overall_risk == ContractRiskLevel.HIGH.value
    # 对照修改视图
    assert len(result.redline) == 1
    # 依据核验：f1 带动 basis 且可核验
    assert result.citation_total == 1
    assert result.citation_verified == 1
    assert result.findings[0].basis_source_url is not None
    # 未带 basis 的 finding 标记需人工复核（默认）
    assert result.findings[1].basis is None
    # 落库
    assert len(session.added) == 1
    assert session.added[0].overall_risk == ContractRiskLevel.HIGH.value
    assert session.added[0].metadata_["original_name"] == "lease.docx"


@pytest.mark.asyncio
async def test_review_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.contract_review.get_llm_provider", lambda: MockProvider()
    )
    svc = _service()
    req = ContractReviewRequest(
        text="押金一律不予退还，乙方不得异议。", stance=ReviewStance.NEUTRAL
    )
    result = await svc.review_text(req, user=_user())
    assert result.status == ContractReviewStatus.DONE.value
    assert len(result.findings) >= 1


@pytest.mark.asyncio
async def test_review_llm_failure_marks_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    class _BrokenProvider:
        async def complete_json(self, *a: Any, **k: Any) -> dict[str, Any]:
            raise AgentError("llm", "no api key")

    monkeypatch.setattr(
        "app.services.contract_review.get_llm_provider", lambda: _BrokenProvider()
    )
    session = _FakeSession()
    svc = _service(session)

    result = await svc.review_document(
        _parsed(),
        original_name=None,
        stance=ReviewStance.NEUTRAL,
        contract_type="服务合同",
        project_id=None,
        user=_user(),
    )

    assert result.status == ContractReviewStatus.FAILED.value
    assert result.findings == []
    assert result.redline == []
    # 失败仍落库（可追溯），contract_type 回退到入参
    assert len(session.added) == 1
    assert result.contract_type == "服务合同"


# ============== API 层 ==============
def _read(review_id: UUID) -> ContractReviewRead:
    from datetime import UTC, datetime

    return ContractReviewRead(
        id=review_id,
        contract_type="房屋租赁合同",
        stance=ReviewStance.NEUTRAL.value,
        overall_risk=ContractRiskLevel.HIGH.value,
        summary="存在押金风险。",
        status=ContractReviewStatus.DONE.value,
        original_name="lease.docx",
        project_id=None,
        findings=[
            ContractFinding(
                id="f1",
                level=ContractRiskLevel.HIGH,
                clause_no="第3条",
                clause_text="押金不予退还。",
                issue="显失公平",
                suggestion="改为可退还",
            )
        ],
        redline=[],
        risk_counts={ContractRiskLevel.HIGH.value: 1},
        citation_total=0,
        citation_verified=0,
        created_at=datetime.now(UTC),
    )


def _make_api_app(service: Any, user: CorePrincipal | None = None) -> FastAPI:
    app = FastAPI()
    app.include_router(contract_router)
    app.dependency_overrides[get_contract_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: user or _user()

    async def _get_db_override() -> Any:
        yield MagicMock()

    app.dependency_overrides[get_db] = _get_db_override
    return app


@pytest.mark.asyncio
async def test_api_create_text_review() -> None:
    svc = MagicMock()
    rid = uuid4()
    from unittest.mock import AsyncMock

    svc.review_text = AsyncMock(return_value=_read(rid))
    app = _make_api_app(svc)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            "/contract/reviews/text",
            json={"text": "押金一律不予退还，乙方不得异议。", "stance": "neutral"},
        )
    assert resp.status_code == 201
    body = resp.json()
    assert body["id"] == str(rid)
    assert body["overall_risk"] == ContractRiskLevel.HIGH.value


@pytest.mark.asyncio
async def test_api_get_review_not_found() -> None:
    from unittest.mock import AsyncMock

    from app.core.errors import NotFoundError

    svc = MagicMock()
    svc.get_review = AsyncMock(return_value=None)
    app = _make_api_app(svc)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        with pytest.raises(NotFoundError):
            await c.get(f"/contract/reviews/{uuid4()}")
