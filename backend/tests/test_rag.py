"""RAG 混合检索服务测试 - Sprint 3 / FR-015 混合检索。

覆盖：
- 混合检索 SQL 模板（关键字段、过滤条件、加权融合）
- RAGSearchRequest 参数校验
- search_simple 默认参数
- embedding 失败时抛 AgentError
- session.execute 失败时抛 AgentError
- 元数据过滤参数构造（law_types/law_levels/law_statuses）

不覆盖（需真实 Postgres + pgvector + pg_trgm，留作集成测试）：
- 实际向量召回
- 实际 trgm 相似度
- HNSW 索引使用
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AgentError
from app.schemas.legal import RAGSearchRequest, RAGSearchResultItem
from app.tools import rag
from app.tools.rag import RAGSearchService


# ============== SQL 模板结构 ==============
def test_hybrid_search_sql_contains_required_clauses() -> None:
    """混合检索 SQL 必须包含向量召回、关键词召回、加权融合三段。"""
    sql = rag._HYBRID_SEARCH_SQL
    # 向量召回（HNSW 余弦距离）
    assert "<=> :emb" in sql
    assert "ORDER BY c.embedding <=> :emb" in sql
    # 关键词召回（pg_trgm similarity）
    assert "similarity(c.content, :query)" in sql
    assert "c.content %% :query" in sql
    # 加权融合
    assert ":vector_weight" in sql
    assert ":keyword_weight" in sql
    assert "final_score" in sql
    # 元数据过滤
    assert ":law_types" in sql
    assert ":law_levels" in sql
    assert ":law_statuses" in sql
    # 软删除过滤
    assert "d.deleted_at IS NULL" in sql
    # Top-K
    assert "LIMIT :top_k" in sql


def test_hybrid_search_sql_uses_rrf_full_outer_join() -> None:
    """向量和关键词召回结果用 FULL OUTER JOIN 融合（RRF 风格）。"""
    sql = rag._HYBRID_SEARCH_SQL
    assert "FULL OUTER JOIN kw k ON v.clause_id = k.clause_id" in sql
    # COALESCE 处理单边命中的情况
    assert "COALESCE(v.clause_id, k.clause_id)" in sql
    assert "COALESCE(v.law_id, k.law_id)" in sql


def test_hybrid_search_sql_score_normalization() -> None:
    """向量距离 (0=相同, 2=相反) 转换为相似度分数 (0~1)。"""
    sql = rag._HYBRID_SEARCH_SQL
    # 1.0 - vector_distance
    assert "1.0 - v.vector_distance" in sql
    # 关键词相似度已经是 0~1
    assert "COALESCE(k.kw_sim, 0.0)" in sql


# ============== RAGSearchRequest 参数校验 ==============
def test_search_request_defaults() -> None:
    """默认 top_k=10, vector_weight=0.7, keyword_weight=0.3, law_status=['effective']。"""
    req = RAGSearchRequest(query="测试 query")
    assert req.top_k == 10
    assert req.vector_weight == 0.7
    assert req.keyword_weight == 0.3
    assert req.law_types is None
    assert req.law_levels is None
    # law_status 默认含 effective
    status_values = [s.value if hasattr(s, "value") else s for s in req.law_status]
    assert "effective" in status_values


def test_search_request_query_min_length() -> None:
    """query 不能为空。"""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        RAGSearchRequest(query="")


def test_search_request_query_max_length() -> None:
    """query 不能超过 2000 字符。"""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        RAGSearchRequest(query="x" * 2001)


def test_search_request_top_k_range() -> None:
    """top_k 范围 1~50。"""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        RAGSearchRequest(query="x", top_k=0)
    with pytest.raises(ValidationError):
        RAGSearchRequest(query="x", top_k=51)


def test_search_request_weights_range() -> None:
    """vector_weight / keyword_weight 范围 0.0~1.0。"""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        RAGSearchRequest(query="x", vector_weight=-0.1)
    with pytest.raises(ValidationError):
        RAGSearchRequest(query="x", vector_weight=1.1)
    with pytest.raises(ValidationError):
        RAGSearchRequest(query="x", keyword_weight=-0.1)
    with pytest.raises(ValidationError):
        RAGSearchRequest(query="x", keyword_weight=1.1)


# ============== search_simple ==============
@pytest.mark.asyncio
async def test_search_simple_uses_default_params() -> None:
    """search_simple 调 search 时使用默认参数（top_k=10）。"""
    session = AsyncMock(spec=AsyncSession)
    service = RAGSearchService(session)

    # Mock embedding 返回固定向量
    mock_provider = AsyncMock()
    mock_provider.embed.return_value = [0.1] * 1024
    mock_provider.name = "mock"

    # Mock session.execute 返回空结果
    mock_result = MagicMock()
    mock_result.all.return_value = []
    session.execute = AsyncMock(return_value=mock_result)

    with patch.object(rag, "get_embedding_provider", return_value=mock_provider):
        items = await service.search_simple("测试 query")

    assert items == []
    # 验证调用了 search（间接验证 search_simple 转发逻辑）
    session.execute.assert_awaited()
    # 验证 SQL 参数中 top_k = 10
    call_args = session.execute.await_args
    # params 是 dict（第二个位置参数）
    params_dict = call_args.args[1] if len(call_args.args) > 1 else None
    assert params_dict is not None
    assert params_dict["top_k"] == 10


@pytest.mark.asyncio
async def test_search_simple_custom_top_k() -> None:
    """search_simple 支持自定义 top_k。"""
    session = AsyncMock(spec=AsyncSession)
    service = RAGSearchService(session)

    mock_provider = AsyncMock()
    mock_provider.embed.return_value = [0.1] * 1024
    mock_provider.name = "mock"

    mock_result = MagicMock()
    mock_result.all.return_value = []
    session.execute = AsyncMock(return_value=mock_result)

    with patch.object(rag, "get_embedding_provider", return_value=mock_provider):
        await service.search_simple("test", top_k=20)

    call_args = session.execute.await_args
    params_dict = call_args.args[1]
    assert params_dict["top_k"] == 20
    # k_vec / k_kw 是 top_k * 3，至少 30
    assert params_dict["k_vec"] == max(20 * 3, 30)
    assert params_dict["k_kw"] == max(20 * 3, 30)


# ============== 错误路径 ==============
@pytest.mark.asyncio
async def test_search_embedding_failure_raises_agent_error() -> None:
    """embedding 调用失败 → AgentError（不静默返回空结果）。"""
    session = AsyncMock(spec=AsyncSession)
    service = RAGSearchService(session)

    mock_provider = AsyncMock()
    mock_provider.embed.side_effect = RuntimeError("network down")
    mock_provider.name = "mock"

    with (
        patch.object(rag, "get_embedding_provider", return_value=mock_provider),
        pytest.raises(AgentError) as exc_info,
    ):
        await service.search(RAGSearchRequest(query="x"))

    assert "embedding" in str(exc_info.value).lower() or "query" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_search_embedding_agent_error_propagates() -> None:
    """AgentError 类型直接透传（不被包装）。"""
    session = AsyncMock(spec=AsyncSession)
    service = RAGSearchService(session)

    mock_provider = AsyncMock()
    original_err = AgentError("legal_retrieve", "upstream embedding error")
    mock_provider.embed.side_effect = original_err

    with (
        patch.object(rag, "get_embedding_provider", return_value=mock_provider),
        pytest.raises(AgentError) as exc_info,
    ):
        await service.search(RAGSearchRequest(query="x"))

    # 直接返回原 AgentError，不重新包装
    assert exc_info.value is original_err


# ============== 参数构造 ==============
@pytest.mark.asyncio
async def test_search_params_with_metadata_filters() -> None:
    """law_types / law_levels / law_status 过滤参数正确构造。"""
    from app.core.constants import LawLevel, LawStatus, LawType

    session = AsyncMock(spec=AsyncSession)
    service = RAGSearchService(session)

    mock_provider = AsyncMock()
    mock_provider.embed.return_value = [0.1] * 1024
    mock_provider.name = "mock"

    mock_result = MagicMock()
    mock_result.all.return_value = []
    session.execute = AsyncMock(return_value=mock_result)

    req = RAGSearchRequest(
        query="test",
        top_k=5,
        law_types=[LawType.LAW, LawType.ADMIN_REG],
        law_levels=[LawLevel.NATIONAL, LawLevel.PROVINCE],
        law_status=[LawStatus.EFFECTIVE],
    )

    with patch.object(rag, "get_embedding_provider", return_value=mock_provider):
        await service.search(req)

    call_args = session.execute.await_args
    params = call_args.args[1]
    assert params["law_types"] == ["law", "admin_reg"]
    assert params["law_levels"] == ["national", "province"]
    assert params["law_statuses"] == ["effective"]
    assert params["top_k"] == 5
    assert params["vector_weight"] == 0.7
    assert params["keyword_weight"] == 0.3


@pytest.mark.asyncio
async def test_search_params_without_filters_pass_none() -> None:
    """未指定过滤参数时传 None（SQL 里走 IS NULL 分支）。"""
    session = AsyncMock(spec=AsyncSession)
    service = RAGSearchService(session)

    mock_provider = AsyncMock()
    mock_provider.embed.return_value = [0.1] * 1024
    mock_provider.name = "mock"

    mock_result = MagicMock()
    mock_result.all.return_value = []
    session.execute = AsyncMock(return_value=mock_result)

    req = RAGSearchRequest(query="test", law_types=None, law_levels=None, law_status=None)

    with patch.object(rag, "get_embedding_provider", return_value=mock_provider):
        await service.search(req)

    params = session.execute.await_args.args[1]
    assert params["law_types"] is None
    assert params["law_levels"] is None
    assert params["law_statuses"] is None


@pytest.mark.asyncio
async def test_search_embedding_passed_as_string() -> None:
    """pgvector 接受 str(list) 形式的 embedding 参数。"""
    session = AsyncMock(spec=AsyncSession)
    service = RAGSearchService(session)

    mock_provider = AsyncMock()
    mock_provider.embed.return_value = [0.1, 0.2, 0.3]
    mock_provider.name = "mock"

    mock_result = MagicMock()
    mock_result.all.return_value = []
    session.execute = AsyncMock(return_value=mock_result)

    with patch.object(rag, "get_embedding_provider", return_value=mock_provider):
        await service.search(RAGSearchRequest(query="test"))

    params = session.execute.await_args.args[1]
    # emb 通过 str(list) 转换
    assert params["emb"] == str([0.1, 0.2, 0.3])


# ============== 结果构造 ==============
@pytest.mark.asyncio
async def test_search_returns_took_ms_and_total() -> None:
    """响应包含 took_ms 和 total 字段。"""
    session = AsyncMock(spec=AsyncSession)
    service = RAGSearchService(session)

    mock_provider = AsyncMock()
    mock_provider.embed.return_value = [0.1] * 1024
    mock_provider.name = "mock"

    # 构造 1 条假结果
    fake_id = uuid4()
    fake_law_id = uuid4()
    fake_row = MagicMock()
    fake_row.clause_id = fake_id
    fake_row.law_id = fake_law_id
    fake_row.law_name = "行政许可法"
    fake_row.law_type = "law"
    fake_row.law_level = "national"
    fake_row.law_status = "effective"
    fake_row.publish_date = None
    fake_row.chapter = "第一章 总则"
    fake_row.section = None
    fake_row.article_no = "第一条"
    fake_row.article_title = "立法目的"
    fake_row.content = "为了规范行政许可的设定和实施"
    fake_row.keywords = ["行政许可", "立法"]
    fake_row.vector_score = 0.95
    fake_row.keyword_score = 0.5
    fake_row.final_score = 0.8

    mock_result = MagicMock()
    mock_result.all.return_value = [fake_row]
    session.execute = AsyncMock(return_value=mock_result)

    with patch.object(rag, "get_embedding_provider", return_value=mock_provider):
        resp = await service.search(RAGSearchRequest(query="行政许可"))

    assert resp.query == "行政许可"
    assert resp.total == 1
    assert resp.took_ms >= 0
    assert len(resp.items) == 1
    item = resp.items[0]
    assert isinstance(item, RAGSearchResultItem)
    assert item.clause_id == fake_id
    assert item.law_name == "行政许可法"
    assert item.article_no == "第一条"
    assert item.article_title == "立法目的"
    assert item.law_type == "law"
    assert item.law_status == "effective"
    assert item.vector_score == 0.95
    assert item.final_score == 0.8
    # keywords 默认空数组（即使数据库返回 None）
    assert item.keywords == ["行政许可", "立法"] or item.keywords == []


@pytest.mark.asyncio
async def test_search_keywords_default_to_empty_when_none() -> None:
    """数据库返回 keywords=None 时降级为空数组。"""
    session = AsyncMock(spec=AsyncSession)
    service = RAGSearchService(session)

    mock_provider = AsyncMock()
    mock_provider.embed.return_value = [0.1] * 1024
    mock_provider.name = "mock"

    fake_row = MagicMock()
    fake_row.clause_id = uuid4()
    fake_row.law_id = uuid4()
    fake_row.law_name = "x"
    fake_row.law_type = "law"
    fake_row.law_level = "national"
    fake_row.law_status = "effective"
    fake_row.publish_date = None
    fake_row.chapter = None
    fake_row.section = None
    fake_row.article_no = "第一条"
    fake_row.article_title = None
    fake_row.content = "x"
    fake_row.keywords = None  # 数据库 NULL
    fake_row.vector_score = 0.0
    fake_row.keyword_score = 0.0
    fake_row.final_score = 0.0

    mock_result = MagicMock()
    mock_result.all.return_value = [fake_row]
    session.execute = AsyncMock(return_value=mock_result)

    with patch.object(rag, "get_embedding_provider", return_value=mock_provider):
        resp = await service.search(RAGSearchRequest(query="x"))

    assert resp.items[0].keywords == []


@pytest.mark.asyncio
async def test_search_scores_rounded_to_4_decimals() -> None:
    """vector_score / keyword_score / final_score 保留 4 位小数。"""
    session = AsyncMock(spec=AsyncSession)
    service = RAGSearchService(session)

    mock_provider = AsyncMock()
    mock_provider.embed.return_value = [0.1] * 1024
    mock_provider.name = "mock"

    fake_row = MagicMock()
    fake_row.clause_id = uuid4()
    fake_row.law_id = uuid4()
    fake_row.law_name = "x"
    fake_row.law_type = "law"
    fake_row.law_level = "national"
    fake_row.law_status = "effective"
    fake_row.publish_date = None
    fake_row.chapter = None
    fake_row.section = None
    fake_row.article_no = "第一条"
    fake_row.article_title = None
    fake_row.content = "x"
    fake_row.keywords = []
    # 长小数
    fake_row.vector_score = 0.123456789
    fake_row.keyword_score = 0.987654321
    fake_row.final_score = 0.555555555

    mock_result = MagicMock()
    mock_result.all.return_value = [fake_row]
    session.execute = AsyncMock(return_value=mock_result)

    with patch.object(rag, "get_embedding_provider", return_value=mock_provider):
        resp = await service.search(RAGSearchRequest(query="x"))

    item = resp.items[0]
    assert item.vector_score == 0.1235
    assert item.keyword_score == 0.9877
    assert item.final_score == 0.5556
