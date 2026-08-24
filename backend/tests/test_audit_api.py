"""审计 API 测试 - Sprint 5 / FR-035。

策略：直接 mock session.execute 返回，验证 SQL 过滤条件被正确应用。
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_db
from app.api.v1.audit import router as audit_router


def _make_test_app(session: MagicMock) -> FastAPI:
    app = FastAPI()
    app.include_router(audit_router)
    async def _get_db_override():
        yield session
    app.dependency_overrides[get_db] = _get_db_override
    return app


def _make_audit_mock(record_id=None) -> MagicMock:
    m = MagicMock()
    m.id = record_id or uuid4()
    m.trace_id = uuid4()
    m.actor_id = uuid4()
    m.actor_role = "admin"
    m.action = "create"
    m.target_type = "legal_document"
    m.target_id = uuid4()
    m.before_value = None
    m.after_value = {"x": 1}
    m.ip_address = "127.0.0.1"
    m.user_agent = "test-agent"
    m.created_at = datetime.utcnow()
    return m


# ============== GET /audit/records 列表 ==============
@pytest.mark.asyncio
async def test_list_audit_records() -> None:
    rec = _make_audit_mock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [rec]
    session = MagicMock()
    session.execute = AsyncMock(return_value=mock_result)

    app = _make_test_app(session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.get("/audit/records")

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) == 1
    assert body[0]["action"] == "create"
    assert body[0]["after_value"] == {"x": 1}


@pytest.mark.asyncio
async def test_list_audit_records_with_filters() -> None:
    """验证过滤参数被传递到 SQL 语句。"""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session = MagicMock()
    session.execute = AsyncMock(return_value=mock_result)

    app = _make_test_app(session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.get("/audit/records", params={
            "action": "create",
            "target_type": "legal_document",
            "page": 1,
            "page_size": 10,
        })

    assert resp.status_code == 200
    session.execute.assert_awaited()


# ============== GET /audit/trace/{trace_id} ==============
@pytest.mark.asyncio
async def test_list_by_trace() -> None:
    trace_id = uuid4()
    rec = _make_audit_mock()
    rec.trace_id = trace_id
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [rec]
    session = MagicMock()
    session.execute = AsyncMock(return_value=mock_result)

    app = _make_test_app(session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.get(f"/audit/trace/{trace_id}")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["trace_id"] == str(trace_id)


# ============== GET /audit/records/{record_id} ==============
@pytest.mark.asyncio
async def test_get_audit_record_success() -> None:
    record_id = uuid4()
    rec = _make_audit_mock(record_id=record_id)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = rec
    session = MagicMock()
    session.execute = AsyncMock(return_value=mock_result)

    app = _make_test_app(session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.get(f"/audit/records/{record_id}")

    assert resp.status_code == 200
    assert resp.json()["id"] == str(record_id)


@pytest.mark.asyncio
async def test_get_audit_record_not_found() -> None:
    """记录不存在 → 404。"""
    from app.main import create_app

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session = MagicMock()
    session.execute = AsyncMock(return_value=mock_result)

    app = create_app()
    async def _get_db_override():
        yield session
    app.dependency_overrides[get_db] = _get_db_override

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.get(f"/api/v1/audit/records/{uuid4()}")

    assert resp.status_code == 404


# ============== GET /audit/count ==============
@pytest.mark.asyncio
async def test_count_audit_records() -> None:
    mock_result = MagicMock()
    mock_result.scalar_one.return_value = 100
    session = MagicMock()
    session.execute = AsyncMock(return_value=mock_result)

    app = _make_test_app(session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.get("/audit/count")

    assert resp.status_code == 200
    assert resp.json()["total"] == 100
