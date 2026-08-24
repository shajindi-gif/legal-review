"""法规库管理 API 测试 - Sprint 3 / FR-011~FR-020。

策略：用一个独立的 FastAPI app 只挂 legal router，通过 dependency_overrides
注入 mock service / audit / actor，避免依赖真实 DB / 鉴权 / 审计。

覆盖：
- POST /legal/laws 单部法规导入（含切分）
- POST /legal/import 批量导入（含容错）
- GET /legal/laws 法规列表
- GET /legal/laws/{law_id} 法规详情
- GET /legal/laws/{law_id}/validity 时效检查
- POST /legal/laws/{law_id}/status 状态变更
- POST /legal/search RAG 检索
- HTTP 错误响应（NotFoundError → 404）
- 审计日志被调用
"""
from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_actor, get_audit_service, get_db
from app.api.v1.legal import (
    get_legal_library_service,
    get_rag_service,
)
from app.api.v1.legal import (
    router as legal_router,
)
from app.core.errors import NotFoundError
from app.schemas.legal import (
    LawTimeValidity,
    LegalDocumentRead,
    LegalLibraryImportResponse,
    RAGSearchRequest,
    RAGSearchResponse,
    RAGSearchResultItem,
)


# ============== 测试 app ==============
def _make_test_app(
    *,
    library_service: Any = None,
    rag_service: Any = None,
    audit_service: Any = None,
    actor: dict | None = None,
) -> FastAPI:
    """构造独立测试 app（只挂 legal router）。"""
    app = FastAPI()
    app.include_router(legal_router)

    if library_service is not None:
        async def _get_library():
            yield library_service
        app.dependency_overrides[get_legal_library_service] = _get_library
    if rag_service is not None:
        async def _get_rag():
            yield rag_service
        app.dependency_overrides[get_rag_service] = _get_rag
    if audit_service is not None:
        app.dependency_overrides[get_audit_service] = lambda: audit_service
    if actor is not None:
        app.dependency_overrides[get_actor] = lambda: actor

    # 拦截 db 依赖（实际不会用）
    async def _get_db_override():
        yield MagicMock()

    app.dependency_overrides[get_db] = _get_db_override

    return app


# ============== POST /legal/laws 单部导入 ==============
@pytest.mark.asyncio
async def test_create_law_returns_201() -> None:
    """单部法规导入返回 201 + 读取响应。"""
    law_id = uuid4()
    mock_law = MagicMock()
    mock_law.id = law_id
    mock_law.law_name = "行政许可法"
    mock_law.issuing_authority = "全国人大常委会"
    mock_law.publish_date = date(2024, 1, 1)
    mock_law.effective_date = None
    mock_law.expire_date = None
    mock_law.law_type = "law"
    mock_law.law_level = "national"
    mock_law.version = "v1.0.0"
    mock_law.status = "effective"
    mock_law.keywords = ["test"]
    mock_law.clauses = []
    mock_law.created_at = date(2024, 1, 1)

    lib = MagicMock()
    lib.import_law = AsyncMock(return_value=mock_law)
    lib._session = MagicMock()
    lib._session.commit = AsyncMock()

    audit = MagicMock()
    audit.log = AsyncMock()

    app = _make_test_app(
        library_service=lib, audit_service=audit,
        actor={"user_id": "u1", "role": "librarian", "ip": "127.0.0.1"},
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.post(
            "/legal/laws",
            json={
                "law_name": "行政许可法",
                "issuing_authority": "全国人大常委会",
                "publish_date": "2024-01-01",
                "law_type": "law",
                "law_level": "national",
                "version": "v1.0.0",
                "raw_text": "第一条 测试内容。",
                "keywords": ["test"],
            },
        )

    assert resp.status_code == 201
    body = resp.json()
    assert body["id"] == str(law_id)
    assert body["law_name"] == "行政许可法"
    assert body["clause_count"] == 0
    # 审计被调用
    audit.log.assert_awaited()
    # commit 被调用
    lib._session.commit.assert_awaited()


@pytest.mark.asyncio
async def test_create_law_returns_clause_count() -> None:
    """返回响应中含 clauses 数量。"""
    mock_law = MagicMock()
    mock_law.id = uuid4()
    mock_law.law_name = "x"
    mock_law.issuing_authority = "y"
    mock_law.publish_date = date(2024, 1, 1)
    mock_law.effective_date = None
    mock_law.expire_date = None
    mock_law.law_type = "law"
    mock_law.law_level = "national"
    mock_law.version = "v1.0.0"
    mock_law.status = "effective"
    mock_law.keywords = []
    mock_law.created_at = date(2024, 1, 1)
    # 3 个 clauses
    mock_law.clauses = [MagicMock(), MagicMock(), MagicMock()]

    lib = MagicMock()
    lib.import_law = AsyncMock(return_value=mock_law)
    lib._session = MagicMock()
    lib._session.commit = AsyncMock()

    app = _make_test_app(
        library_service=lib, audit_service=MagicMock(log=AsyncMock()),
        actor={"user_id": "u1", "role": "librarian", "ip": "127.0.0.1"},
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.post("/legal/laws", json={
            "law_name": "x", "issuing_authority": "y",
            "publish_date": "2024-01-01", "law_type": "law",
            "law_level": "national", "raw_text": "第一条 x。",
        })

    assert resp.status_code == 201
    assert resp.json()["clause_count"] == 3


# ============== POST /legal/import 批量导入 ==============
@pytest.mark.asyncio
async def test_import_batch_success() -> None:
    """批量导入全部成功。"""
    result = LegalLibraryImportResponse(
        total=2, succeeded=2, failed=0, errors=[], law_ids=[uuid4(), uuid4()]
    )
    lib = MagicMock()
    lib.batch_import = AsyncMock(return_value=result)

    audit = MagicMock()
    audit.log = AsyncMock()

    app = _make_test_app(
        library_service=lib, audit_service=audit,
        actor={"user_id": "u1", "role": "librarian", "ip": "127.0.0.1"},
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.post("/legal/import", json={"documents": [
            {
                "law_name": "法1", "issuing_authority": "x",
                "publish_date": "2024-01-01", "law_type": "law",
                "law_level": "national", "raw_text": "第一条 x。",
            },
            {
                "law_name": "法2", "issuing_authority": "y",
                "publish_date": "2024-01-01", "law_type": "law",
                "law_level": "national", "raw_text": "第一条 y。",
            },
        ]})

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert body["succeeded"] == 2
    assert body["failed"] == 0
    audit.log.assert_awaited()


@pytest.mark.asyncio
async def test_import_batch_with_failures() -> None:
    """批量导入返回失败条目。"""
    result = LegalLibraryImportResponse(
        total=3, succeeded=2, failed=1,
        errors=[{"index": 1, "law_name": "bad", "error": "切分失败"}],
        law_ids=[uuid4(), uuid4()],
    )
    lib = MagicMock()
    lib.batch_import = AsyncMock(return_value=result)

    app = _make_test_app(
        library_service=lib, audit_service=MagicMock(log=AsyncMock()),
        actor={"user_id": "u1", "role": "librarian", "ip": "127.0.0.1"},
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.post("/legal/import", json={"documents": []})

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert body["failed"] == 1
    assert len(body["errors"]) == 1


# ============== GET /legal/laws 列表 ==============
@pytest.mark.asyncio
async def test_list_laws_returns_list() -> None:
    """法规列表返回数组。"""
    items = [
        LegalDocumentRead(
            id=uuid4(), law_name="法1", issuing_authority="x",
            publish_date=date(2024, 1, 1), effective_date=None, expire_date=None,
            law_type="law", law_level="national", version="v1.0.0",
            status="effective", keywords=[], clause_count=3,
            created_at=date(2024, 1, 1),
        ),
    ]
    lib = MagicMock()
    lib.list_laws = AsyncMock(return_value=(items, 1))

    app = _make_test_app(library_service=lib)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.get("/legal/laws")

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) == 1
    assert body[0]["law_name"] == "法1"


@pytest.mark.asyncio
async def test_list_laws_with_filters() -> None:
    """列表支持过滤参数。"""
    lib = MagicMock()
    lib.list_laws = AsyncMock(return_value=([], 0))

    app = _make_test_app(library_service=lib)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.get(
            "/legal/laws",
            params={
                "law_type": "law", "law_level": "national",
                "status": "effective", "keyword": "test",
                "page": 1, "page_size": 10,
            },
        )

    assert resp.status_code == 200
    # 验证过滤参数被传递
    call_args = lib.list_laws.await_args
    assert call_args.kwargs["law_type"] == "law"
    assert call_args.kwargs["law_level"] == "national"
    assert call_args.kwargs["status"] == "effective"
    assert call_args.kwargs["keyword"] == "test"
    assert call_args.kwargs["page"] == 1
    assert call_args.kwargs["page_size"] == 10


# ============== GET /legal/laws/{law_id} 详情 ==============
@pytest.mark.asyncio
async def test_get_law_returns_200() -> None:
    law_id = uuid4()
    mock_law = MagicMock()
    mock_law.id = law_id
    mock_law.law_name = "x"
    mock_law.issuing_authority = "y"
    mock_law.publish_date = date(2024, 1, 1)
    mock_law.effective_date = None
    mock_law.expire_date = None
    mock_law.law_type = "law"
    mock_law.law_level = "national"
    mock_law.version = "v1.0.0"
    mock_law.status = "effective"
    mock_law.keywords = []
    mock_law.created_at = date(2024, 1, 1)
    mock_law.clauses = [MagicMock(), MagicMock()]

    lib = MagicMock()
    lib.get_law_with_clauses = AsyncMock(return_value=mock_law)

    app = _make_test_app(library_service=lib)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.get(f"/legal/laws/{law_id}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == str(law_id)
    assert body["clause_count"] == 2


# ============== GET /legal/laws/{law_id}/validity 时效 ==============
@pytest.mark.asyncio
async def test_check_validity_returns_200() -> None:
    law_id = uuid4()
    validity = LawTimeValidity(
        law_id=law_id, law_name="x", status="effective",
        is_effective=True, expire_date=None, days_to_expire=None,
        warning=None,
    )
    lib = MagicMock()
    lib.check_time_validity = AsyncMock(return_value=validity)

    app = _make_test_app(library_service=lib)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.get(f"/legal/laws/{law_id}/validity")

    assert resp.status_code == 200
    body = resp.json()
    assert body["is_effective"] is True
    assert body["warning"] is None


# ============== POST /legal/laws/{law_id}/status 状态变更 ==============
@pytest.mark.asyncio
async def test_update_status_returns_200() -> None:
    law_id = uuid4()
    mock_law = MagicMock()
    mock_law.id = law_id
    mock_law.law_name = "x"
    mock_law.issuing_authority = "y"
    mock_law.publish_date = date(2024, 1, 1)
    mock_law.effective_date = None
    mock_law.expire_date = None
    mock_law.law_type = "law"
    mock_law.law_level = "national"
    mock_law.version = "v1.0.0"
    mock_law.status = "repealed"
    mock_law.keywords = []
    mock_law.created_at = date(2024, 1, 1)

    lib = MagicMock()
    lib.update_law_status = AsyncMock(return_value=mock_law)
    lib._session = MagicMock()
    lib._session.commit = AsyncMock()

    app = _make_test_app(
        library_service=lib, audit_service=MagicMock(log=AsyncMock()),
        actor={"user_id": "u1", "role": "admin", "ip": "127.0.0.1"},
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.post(
            f"/legal/laws/{law_id}/status",
            params={"new_status": "repealed"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "repealed"


# ============== POST /legal/search RAG 检索 ==============
@pytest.mark.asyncio
async def test_rag_search_returns_results() -> None:
    item = RAGSearchResultItem(
        clause_id=uuid4(), law_id=uuid4(), law_name="行政许可法",
        law_type="law", law_level="national", law_status="effective",
        publish_date=None, chapter="第一章", section=None,
        article_no="第一条", article_title="立法目的",
        content="为了规范行政许可的设定和实施",
        keywords=["行政许可"],
        vector_score=0.95, keyword_score=0.5, final_score=0.8,
    )
    response = RAGSearchResponse(
        query="行政许可", total=1, items=[item], took_ms=42,
    )
    rag = MagicMock()
    rag.search = AsyncMock(return_value=response)

    app = _make_test_app(rag_service=rag)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.post("/legal/search", json={
            "query": "行政许可",
            "top_k": 10,
        })

    assert resp.status_code == 200
    body = resp.json()
    assert body["query"] == "行政许可"
    assert body["total"] == 1
    assert body["took_ms"] == 42
    assert len(body["items"]) == 1
    assert body["items"][0]["law_name"] == "行政许可法"
    assert body["items"][0]["article_no"] == "第一条"


@pytest.mark.asyncio
async def test_rag_search_with_filters() -> None:
    response = RAGSearchResponse(
        query="test", total=0, items=[], took_ms=0,
    )
    rag = MagicMock()
    rag.search = AsyncMock(return_value=response)

    app = _make_test_app(rag_service=rag)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.post("/legal/search", json={
            "query": "test",
            "top_k": 20,
            "law_types": ["law", "admin_reg"],
            "law_levels": ["national"],
            "law_status": ["effective"],
            "vector_weight": 0.8,
            "keyword_weight": 0.2,
        })

    assert resp.status_code == 200
    # 验证参数被传递到 RAGSearchRequest
    call_args = rag.search.await_args
    req: RAGSearchRequest = call_args.args[0]
    assert req.query == "test"
    assert req.top_k == 20
    assert req.vector_weight == 0.8
    assert req.keyword_weight == 0.2


# ============== 错误响应 ==============
@pytest.mark.asyncio
async def test_get_law_not_found_returns_404() -> None:
    """NotFoundError 在 main.py 处理为 404，但 legal router 内部已 raise NotFoundError。"""
    lib = MagicMock()
    lib.get_law_with_clauses = AsyncMock(side_effect=NotFoundError("LegalDocument", "x"))

    # 用真实 app（带 AppError 异常处理）
    from app.main import create_app

    app = create_app()
    async def _get_library():
        yield lib
    app.dependency_overrides[get_legal_library_service] = _get_library

    # 拦截 db / audit / actor
    async def _get_db_override():
        yield MagicMock()
    app.dependency_overrides[get_db] = _get_db_override
    app.dependency_overrides[get_audit_service] = lambda: MagicMock(log=AsyncMock())
    app.dependency_overrides[get_actor] = lambda: {"user_id": None, "role": None, "ip": None}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.get(f"/api/v1/legal/laws/{uuid4()}")

    assert resp.status_code == 404
    body = resp.json()
    assert "error" in body
    assert body["error"]["code"] == "not_found"


# ============== 校验错误 ==============
@pytest.mark.asyncio
async def test_create_law_validation_error() -> None:
    """请求体不符合 LegalDocumentCreate schema → 422。"""
    app = _make_test_app(
        library_service=MagicMock(), audit_service=MagicMock(log=AsyncMock()),
        actor={"user_id": "u1", "role": "librarian", "ip": "127.0.0.1"},
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.post("/legal/laws", json={
            "law_name": "",  # min_length=1 触发
            "issuing_authority": "y",
            "publish_date": "2024-01-01",
            "law_type": "law",
            "law_level": "national",
            "raw_text": "x",
        })

    assert resp.status_code == 422
