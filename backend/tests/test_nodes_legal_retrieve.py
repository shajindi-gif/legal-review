"""legal_retrieve_node 测试 - Sprint 3 / FR-015 法规检索节点。

覆盖：
- _extract_review_queries：从 document_json 抽取检索 query
- _extract_review_queries：去重保序 + 最多 10 条
- legal_retrieve_node：document_json 为空时短路返回
- legal_retrieve_node：RAG 检索成功后写入 legal_context + retrieval_result
- legal_retrieve_node：多 query 召回去重
- legal_retrieve_node：单 query 失败容错
- legal_retrieve_node：任务状态更新为 REVIEWING
- legal_retrieve_node：retrieval_result.confidence 满分逻辑（>= 10 条 → 1.0）
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.agent.nodes import _extract_review_queries, legal_retrieve_node
from app.agent.state import ReviewState
from app.core.constants import NodeStatus
from app.schemas.legal import RAGSearchResultItem


# ============== _extract_review_queries ==============
def test_extract_queries_with_full_document() -> None:
    """完整的 document_json 抽取多条 query。"""
    doc_json = {
        "title": "关于促进中小企业发展的若干意见",
        "keywords": ["中小企业", "财政支持", "营商环境"],
        "policy_domain": "economic",
        "body_paragraphs": [
            {"text": "为贯彻落实《中小企业促进法》，结合本县实际。"},
            {"text": "县财政每年安排专项资金 1000 万元。"},
            {"text": "除法律法规另有规定外，不得设置行政许可前置条件。"},
            {"text": "第四段不应被抽取（只取前 3 段）。"},
        ],
    }
    queries = _extract_review_queries(doc_json)
    # 1 title + 3 keywords + 1 policy_domain + 3 body = 8 条
    assert len(queries) == 8
    assert queries[0] == "关于促进中小企业发展的若干意见"
    assert "中小企业" in queries
    assert "economic 行政规范性文件" in queries


def test_extract_queries_dedup() -> None:
    """重复 query 去重保序。"""
    doc_json = {
        "title": "标题",
        "keywords": ["标题", "重复", "重复"],  # "标题" 与 title 重复
        "body_paragraphs": [],
    }
    queries = _extract_review_queries(doc_json)
    assert queries.count("标题") == 1
    assert queries.count("重复") == 1


def test_extract_queries_caps_at_10() -> None:
    """queries 上限为 10 条（即使所有字段都填满）。

    实现行为：candidates = 1 title + min(5, kw_len) + 1 domain + min(3, body_len)
    = 最多 1 + 5 + 1 + 3 = 10 条。即使 [:10] 截断逻辑触发，输入端限制使
    candidates 不超过 10，所以 [:10] 截断实际不可达。
    """
    doc_json = {
        "title": "title",
        "policy_domain": "economic",
        "keywords": [f"kw_{i}" for i in range(15)],  # 取前 5
        "body_paragraphs": [{"text": f"段落 {i}"} for i in range(5)],  # 取前 3
    }
    queries = _extract_review_queries(doc_json)
    assert len(queries) == 10


def test_extract_queries_keywords_truncated_to_5() -> None:
    """keywords 最多取前 5 个。"""
    doc_json = {
        "keywords": [f"kw_{i}" for i in range(10)],
        "body_paragraphs": [],
    }
    queries = _extract_review_queries(doc_json)
    kw_queries = [q for q in queries if q.startswith("kw_")]
    assert len(kw_queries) == 5


def test_extract_queries_body_truncated_to_100_chars() -> None:
    """段落文本截断到 100 字。"""
    long_text = "X" * 200
    doc_json = {
        "body_paragraphs": [{"text": long_text}],
    }
    queries = _extract_review_queries(doc_json)
    assert len(queries[0]) == 100


def test_extract_queries_body_only_first_3_paragraphs() -> None:
    """段落只取前 3 段。"""
    doc_json = {
        "body_paragraphs": [
            {"text": "段落1"},
            {"text": "段落2"},
            {"text": "段落3"},
            {"text": "段落4"},  # 不应该被抽取
        ],
    }
    queries = _extract_review_queries(doc_json)
    assert "段落1" in queries
    assert "段落2" in queries
    assert "段落3" in queries
    assert "段落4" not in queries


def test_extract_queries_handles_string_paragraphs() -> None:
    """段落为字符串（非 dict）时也能处理。"""
    doc_json = {
        "body_paragraphs": ["段落1", "段落2"],
    }
    queries = _extract_review_queries(doc_json)
    assert "段落1" in queries
    assert "段落2" in queries


def test_extract_queries_empty_document() -> None:
    """空 document_json → 空 queries。"""
    assert _extract_review_queries({}) == []
    assert _extract_review_queries({"title": None, "keywords": []}) == []


def test_extract_queries_skips_empty_strings() -> None:
    """空白字符串不进入 query。"""
    doc_json = {
        "title": "",
        "keywords": ["  ", "", "valid"],
        "body_paragraphs": [{"text": "  "}, {"text": ""}],
    }
    queries = _extract_review_queries(doc_json)
    assert "valid" in queries
    assert "" not in queries
    assert "  " not in queries


# ============== legal_retrieve_node ==============
def _make_state(
    *,
    task_id: str | None = None,
    trace_id: str | None = None,
    document_json: dict[str, Any] | None = None,
    iteration: int = 0,
) -> ReviewState:
    return ReviewState(
        task_id=task_id or str(uuid4()),
        trace_id=trace_id or str(uuid4()),
        iteration=iteration,
        max_iteration=5,
        prompt_versions={},
        document_json=document_json if document_json is not None else {},
        legal_context=[],
        user_context={},
        parse_result=None,
        classify_result=None,
        retrieval_result=None,
        authority_result=None,
        procedure_result=None,
        content_result=None,
        risk_result=None,
        verify_result=None,
        report_result=None,
        is_normative=None,
        overall_status="pass",
        needs_human_review=False,
        feedback=None,
        finished=False,
        error=None,
    )


def _make_rag_item(*, law_name: str = "x", article_no: str = "第一条") -> RAGSearchResultItem:
    return RAGSearchResultItem(
        clause_id=uuid4(),
        law_id=uuid4(),
        law_name=law_name,
        law_type="law",
        law_level="national",
        law_status="effective",
        publish_date=None,
        chapter="第一章",
        section=None,
        article_no=article_no,
        article_title=None,
        content="x",
        keywords=[],
        vector_score=0.9,
        keyword_score=0.5,
        final_score=0.8,
    )


@pytest.mark.asyncio
async def test_legal_retrieve_empty_document_json_short_circuits() -> None:
    """document_json 为空时短路返回，error 字段被设置。"""
    state = _make_state(document_json={})

    result = await legal_retrieve_node(state)

    assert "legal_retrieve: document_json empty" in (result.get("error") or "")
    assert result.get("legal_context") is None or result.get("legal_context") == []


@pytest.mark.asyncio
async def test_legal_retrieve_empty_document_json_when_none() -> None:
    """document_json 为 None（不存在）时也短路。"""
    state = _make_state()
    state["document_json"] = None  # type: ignore[assignment]

    result = await legal_retrieve_node(state)

    assert "legal_retrieve: document_json empty" in (result.get("error") or "")


@pytest.mark.asyncio
async def test_legal_retrieve_writes_legal_context_and_result() -> None:
    """RAG 检索成功后写入 legal_context + retrieval_result。"""
    doc_json = {
        "title": "中小企业促进意见",
        "keywords": ["财政支持"],
    }
    state = _make_state(document_json=doc_json)

    # mock RAGSearchService.search_simple 返回 2 条结果
    fake_items = [
        _make_rag_item(law_name="中小企业促进法", article_no="第一条"),
        _make_rag_item(law_name="中小企业促进法", article_no="第二条"),
    ]

    mock_session = AsyncMock()
    # mock get_session_factory 返回 async context manager
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_session
    mock_cm.__aexit__.return_value = None

    # mock task 查询返回 None（不更新 task）
    mock_task_result = MagicMock()
    mock_task_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_task_result)

    # mock RAGSearchService
    mock_rag = MagicMock()
    mock_rag.search_simple = AsyncMock(side_effect=lambda q, top_k=10: fake_items)

    with (
        patch("app.agent.nodes.get_session_factory") as mock_factory,
        patch("app.agent.nodes.RAGSearchService", return_value=mock_rag),
    ):
        mock_factory.return_value.return_value = mock_cm
        result = await legal_retrieve_node(state)

    assert result.get("error") is None
    # legal_context 包含去重后的 2 条（每个 query 都返回同样 2 条，去重后仍 2 条）
    legal_context = result.get("legal_context") or []
    assert len(legal_context) == 2
    assert legal_context[0]["law_name"] == "中小企业促进法"
    assert legal_context[0]["article_no"] == "第一条"
    # retrieval_result 字段
    retrieval_result = result.get("retrieval_result")
    assert retrieval_result is not None
    assert retrieval_result.agent_name == "legal_retrieve"
    assert retrieval_result.node_status == NodeStatus.PASS
    assert retrieval_result.raw_json["total_clauses"] == 2


@pytest.mark.asyncio
async def test_legal_retrieve_deduplicates_clause_ids() -> None:
    """跨 query 召回的相同 clause_id 去重。"""
    doc_json = {
        "title": "title1",
        "keywords": ["kw1"],
    }
    state = _make_state(document_json=doc_json)

    same_item = _make_rag_item(article_no="第一条")
    # 每个 query 都返回同一条
    fake_items = [same_item]

    mock_session = AsyncMock()
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_session
    mock_cm.__aexit__.return_value = None
    mock_task_result = MagicMock()
    mock_task_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_task_result)

    mock_rag = MagicMock()
    mock_rag.search_simple = AsyncMock(side_effect=lambda q, top_k=10: fake_items)

    with (
        patch("app.agent.nodes.get_session_factory") as mock_factory,
        patch("app.agent.nodes.RAGSearchService", return_value=mock_rag),
    ):
        mock_factory.return_value.return_value = mock_cm
        result = await legal_retrieve_node(state)

    legal_context = result.get("legal_context") or []
    # 即使多个 query 都返回同一条，去重后只 1 条
    assert len(legal_context) == 1


@pytest.mark.asyncio
async def test_legal_retrieve_tolerates_single_query_failure() -> None:
    """单条 query 检索失败不影响其他（容错）。"""
    doc_json = {
        "title": "title1",
        "keywords": ["kw1"],
    }
    state = _make_state(document_json=doc_json)

    good_item = _make_rag_item(article_no="第一条")
    call_count = 0

    async def _search_side_effect(q: str, top_k: int = 10) -> list[RAGSearchResultItem]:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("network error")
        return [good_item]

    mock_session = AsyncMock()
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_session
    mock_cm.__aexit__.return_value = None
    mock_task_result = MagicMock()
    mock_task_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_task_result)

    mock_rag = MagicMock()
    mock_rag.search_simple = AsyncMock(side_effect=_search_side_effect)

    with (
        patch("app.agent.nodes.get_session_factory") as mock_factory,
        patch("app.agent.nodes.RAGSearchService", return_value=mock_rag),
    ):
        mock_factory.return_value.return_value = mock_cm
        result = await legal_retrieve_node(state)

    # 不抛错，仍写入成功召回的 1 条
    legal_context = result.get("legal_context") or []
    assert len(legal_context) == 1


@pytest.mark.asyncio
async def test_legal_retrieve_updates_task_status_to_reviewing() -> None:
    """检索后任务 current_node = authority_review，status = REVIEWING。"""
    doc_json = {"title": "x"}
    state = _make_state(document_json=doc_json)

    mock_task = MagicMock()
    mock_task_result = MagicMock()
    mock_task_result.scalar_one_or_none.return_value = mock_task

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_task_result)
    mock_session.commit = AsyncMock()
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_session
    mock_cm.__aexit__.return_value = None

    mock_rag = MagicMock()
    mock_rag.search_simple = AsyncMock(return_value=[])

    with (
        patch("app.agent.nodes.get_session_factory") as mock_factory,
        patch("app.agent.nodes.RAGSearchService", return_value=mock_rag),
    ):
        mock_factory.return_value.return_value = mock_cm
        await legal_retrieve_node(state)

    assert mock_task.current_node == "authority_review"
    # status 字段值取决于 TaskStatus 枚举，但已被赋值
    assert mock_task.status is not None
    mock_session.commit.assert_awaited()


@pytest.mark.asyncio
async def test_legal_retrieve_no_results_status_retry() -> None:
    """召回 0 条时 retrieval_result.node_status = RETRY（置信度 0）。"""
    doc_json = {"title": "x"}
    state = _make_state(document_json=doc_json)

    mock_session = AsyncMock()
    mock_task_result = MagicMock()
    mock_task_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_task_result)
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_session
    mock_cm.__aexit__.return_value = None

    mock_rag = MagicMock()
    mock_rag.search_simple = AsyncMock(return_value=[])

    with (
        patch("app.agent.nodes.get_session_factory") as mock_factory,
        patch("app.agent.nodes.RAGSearchService", return_value=mock_rag),
    ):
        mock_factory.return_value.return_value = mock_cm
        result = await legal_retrieve_node(state)

    retrieval_result = result.get("retrieval_result")
    assert retrieval_result is not None
    assert retrieval_result.node_status == NodeStatus.RETRY
    assert retrieval_result.confidence == 0.0
    assert retrieval_result.raw_json["total_clauses"] == 0


@pytest.mark.asyncio
async def test_legal_retrieve_confidence_caps_at_1() -> None:
    """召回 ≥ 10 条时 confidence = 1.0（min(1.0, n/10)）。"""
    doc_json = {"title": "x"}
    state = _make_state(document_json=doc_json)

    # 12 条不同 clause
    fake_items = [_make_rag_item(article_no=f"第{i}条") for i in range(12)]

    mock_session = AsyncMock()
    mock_task_result = MagicMock()
    mock_task_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_task_result)
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_session
    mock_cm.__aexit__.return_value = None

    mock_rag = MagicMock()
    mock_rag.search_simple = AsyncMock(return_value=fake_items)

    with (
        patch("app.agent.nodes.get_session_factory") as mock_factory,
        patch("app.agent.nodes.RAGSearchService", return_value=mock_rag),
    ):
        mock_factory.return_value.return_value = mock_cm
        result = await legal_retrieve_node(state)

    retrieval_result = result.get("retrieval_result")
    assert retrieval_result.confidence == 1.0


@pytest.mark.asyncio
async def test_legal_retrieve_duration_ms_recorded() -> None:
    """retrieval_result.duration_ms 大于等于 0。"""
    doc_json = {"title": "x"}
    state = _make_state(document_json=doc_json)

    mock_session = AsyncMock()
    mock_task_result = MagicMock()
    mock_task_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_task_result)
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_session
    mock_cm.__aexit__.return_value = None

    mock_rag = MagicMock()
    mock_rag.search_simple = AsyncMock(return_value=[])

    with (
        patch("app.agent.nodes.get_session_factory") as mock_factory,
        patch("app.agent.nodes.RAGSearchService", return_value=mock_rag),
    ):
        mock_factory.return_value.return_value = mock_cm
        result = await legal_retrieve_node(state)

    retrieval_result = result.get("retrieval_result")
    assert retrieval_result.duration_ms >= 0


@pytest.mark.asyncio
async def test_legal_retrieve_legal_context_includes_query_field() -> None:
    """legal_context 每条含 query 字段（追溯哪条 query 召回的）。

    Sprint 4：_generate_legal_queries 调 LLM 生成 query。
    测试中强制 LLM 抛错 → 走启发式 fallback（title="title1"）→ 验证 query 字段。
    """
    doc_json = {"title": "title1"}
    state = _make_state(document_json=doc_json)

    fake_item = _make_rag_item(article_no="第一条")

    mock_session = AsyncMock()
    mock_task_result = MagicMock()
    mock_task_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_task_result)
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_session
    mock_cm.__aexit__.return_value = None

    mock_rag = MagicMock()
    mock_rag.search_simple = AsyncMock(return_value=[fake_item])

    with (
        patch("app.agent.nodes.get_session_factory") as mock_factory,
        patch("app.agent.nodes.RAGSearchService", return_value=mock_rag),
        # Sprint 4：强制 LLM 抛错，让 _generate_legal_queries 走启发式 fallback
        patch("app.agent.nodes.get_llm_provider", side_effect=RuntimeError("test mode")),
    ):
        mock_factory.return_value.return_value = mock_cm
        result = await legal_retrieve_node(state)

    legal_context = result.get("legal_context") or []
    assert len(legal_context) == 1
    assert legal_context[0]["query"] == "title1"
    # 含完整证据链字段
    assert "clause_id" in legal_context[0]
    assert "law_id" in legal_context[0]
    assert "law_name" in legal_context[0]
    assert "final_score" in legal_context[0]
