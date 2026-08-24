"""评测 API 测试 - Sprint 5 / FR-029/031。

策略：用独立 FastAPI app 只挂 eval router，通过 dependency_overrides 注入 mock。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_actor, get_audit_service, get_db
from app.api.v1.eval import get_eval_runner, get_golden_dataset_service
from app.api.v1.eval import router as eval_router
from app.core.errors import NotFoundError, ValidationError
from app.schemas.eval import (
    EvalRunRead,
    GoldenBatchImportResponse,
    GoldenCaseRead,
)


def _make_test_app(
    *,
    dataset_service: Any = None,
    eval_runner: Any = None,
    audit_service: Any = None,
    actor: dict | None = None,
) -> FastAPI:
    app = FastAPI()
    app.include_router(eval_router)

    if dataset_service is not None:
        async def _get_ds():
            yield dataset_service
        app.dependency_overrides[get_golden_dataset_service] = _get_ds
    if eval_runner is not None:
        async def _get_runner():
            yield eval_runner
        app.dependency_overrides[get_eval_runner] = _get_runner
    if audit_service is not None:
        app.dependency_overrides[get_audit_service] = lambda: audit_service
    if actor is not None:
        app.dependency_overrides[get_actor] = lambda: actor

    async def _get_db_override():
        yield MagicMock()
    app.dependency_overrides[get_db] = _get_db_override

    return app


def _make_case_read(case_id=None) -> GoldenCaseRead:
    return GoldenCaseRead(
        id=case_id or uuid4(),
        case_name="测试用例",
        category="normal",
        input_file_path="/tmp/case.txt",
        expected_json={"x": 1},
        expected_status="pass",
        notes=None,
        created_at=datetime.utcnow(),
    )


def _make_run_read(run_id=None) -> EvalRunRead:
    return EvalRunRead(
        id=uuid4(),
        run_id=run_id or uuid4(),
        prompt_version="v1.0.0",
        started_at=datetime.utcnow(),
        finished_at=datetime.utcnow(),
        total_cases=10,
        parse_acc=0.95,
        retrieval_acc=0.90,
        citation_acc=0.85,
        risk_kappa=0.90,
        report_complete=1.0,
        hallucination_rate=0.05,
        overall_pass=True,
        raw_result_path=None,
    )


# ============== POST /eval/golden/import 批量导入 ==============
@pytest.mark.asyncio
async def test_batch_import_golden_success() -> None:
    result = GoldenBatchImportResponse(
        total=2, success=2, failed=0, errors=[],
    )
    ds = MagicMock()
    ds.batch_import = AsyncMock(return_value=result)

    app = _make_test_app(
        dataset_service=ds,
        audit_service=MagicMock(log=AsyncMock()),
        actor={"user_id": "u1", "role": "admin", "ip": "127.0.0.1"},
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.post("/eval/golden/import", json={"cases": [
            {
                "case_name": "c1", "category": "normal",
                "input_file_path": "/tmp/c1.txt",
                "expected_json": {"x": 1}, "expected_status": "pass",
            },
            {
                "case_name": "c2", "category": "authority_violation",
                "input_file_path": "/tmp/c2.txt",
                "expected_json": {"y": 2}, "expected_status": "fail",
            },
        ]})

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert body["success"] == 2


# ============== POST /eval/golden/cases 单条创建 ==============
@pytest.mark.asyncio
async def test_create_golden_case_success() -> None:
    case_read = _make_case_read()
    case_obj = MagicMock()
    case_obj.id = case_read.id
    case_obj.case_name = case_read.case_name
    case_obj.category = case_read.category
    case_obj.input_file_path = case_read.input_file_path
    case_obj.expected_json = case_read.expected_json
    case_obj.expected_status = case_read.expected_status
    case_obj.notes = case_read.notes
    case_obj.created_at = case_read.created_at

    ds = MagicMock()
    ds.batch_import = AsyncMock(return_value=GoldenBatchImportResponse(
        total=1, success=1, failed=0, errors=[],
    ))
    ds.list_cases = AsyncMock(return_value=[case_obj])

    app = _make_test_app(
        dataset_service=ds,
        audit_service=MagicMock(log=AsyncMock()),
        actor={"user_id": "u1", "role": "admin", "ip": "127.0.0.1"},
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.post("/eval/golden/cases", json={
            "case_name": "测试用例",
            "category": "normal",
            "input_file_path": "/tmp/case.txt",
            "expected_json": {"x": 1},
            "expected_status": "pass",
        })

    assert resp.status_code == 201
    body = resp.json()
    assert body["case_name"] == "测试用例"


@pytest.mark.asyncio
async def test_create_golden_case_import_failed() -> None:
    """batch_import 返回 failed → ValidationError → 422。"""
    from app.main import create_app

    ds = MagicMock()
    ds.batch_import = AsyncMock(return_value=GoldenBatchImportResponse(
        total=1, success=0, failed=1, errors=["db error"],
    ))

    app = create_app()
    async def _get_ds():
        yield ds
    app.dependency_overrides[get_golden_dataset_service] = _get_ds
    app.dependency_overrides[get_audit_service] = lambda: MagicMock(log=AsyncMock())
    app.dependency_overrides[get_actor] = lambda: {
        "user_id": "u1", "role": "admin", "ip": "127.0.0.1",
    }
    async def _get_db_override():
        yield MagicMock()
    app.dependency_overrides[get_db] = _get_db_override

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.post("/api/v1/eval/golden/cases", json={
            "case_name": "测试",
            "category": "normal",
            "input_file_path": "/tmp/x.txt",
            "expected_json": {},
            "expected_status": "pass",
        })

    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["code"] == "validation_error"


# ============== GET /eval/golden/cases 列表 ==============
@pytest.mark.asyncio
async def test_list_golden_cases() -> None:
    case_obj = MagicMock()
    case_obj.id = uuid4()
    case_obj.case_name = "c1"
    case_obj.category = "normal"
    case_obj.input_file_path = "/tmp/c1"
    case_obj.expected_json = {}
    case_obj.expected_status = "pass"
    case_obj.notes = None
    case_obj.created_at = datetime.utcnow()

    ds = MagicMock()
    ds.list_cases = AsyncMock(return_value=[case_obj])

    app = _make_test_app(dataset_service=ds)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.get("/eval/golden/cases")

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) == 1
    assert body[0]["case_name"] == "c1"


@pytest.mark.asyncio
async def test_list_golden_cases_with_category_filter() -> None:
    ds = MagicMock()
    ds.list_cases = AsyncMock(return_value=[])

    app = _make_test_app(dataset_service=ds)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.get("/eval/golden/cases", params={"category": "normal"})

    assert resp.status_code == 200
    call_kwargs = ds.list_cases.await_args.kwargs
    assert call_kwargs["category"] == "normal"


# ============== GET /eval/golden/cases/{id} ==============
@pytest.mark.asyncio
async def test_get_golden_case_success() -> None:
    case_id = uuid4()
    case_obj = MagicMock()
    case_obj.id = case_id
    case_obj.case_name = "x"
    case_obj.category = "normal"
    case_obj.input_file_path = "/tmp/x"
    case_obj.expected_json = {}
    case_obj.expected_status = "pass"
    case_obj.notes = None
    case_obj.created_at = datetime.utcnow()

    ds = MagicMock()
    ds.get_case = AsyncMock(return_value=case_obj)

    app = _make_test_app(dataset_service=ds)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.get(f"/eval/golden/cases/{case_id}")

    assert resp.status_code == 200
    assert resp.json()["id"] == str(case_id)


@pytest.mark.asyncio
async def test_get_golden_case_not_found() -> None:
    from app.main import create_app

    ds = MagicMock()
    ds.get_case = AsyncMock(side_effect=NotFoundError("GoldenDataset", "x"))

    app = create_app()
    async def _get_ds():
        yield ds
    app.dependency_overrides[get_golden_dataset_service] = _get_ds
    async def _get_db_override():
        yield MagicMock()
    app.dependency_overrides[get_db] = _get_db_override

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.get(f"/api/v1/eval/golden/cases/{uuid4()}")

    assert resp.status_code == 404


# ============== DELETE /eval/golden/cases/{id} ==============
@pytest.mark.asyncio
async def test_delete_golden_case_success() -> None:
    ds = MagicMock()
    ds.delete_case = AsyncMock(return_value=None)

    app = _make_test_app(
        dataset_service=ds,
        audit_service=MagicMock(log=AsyncMock()),
        actor={"user_id": "u1", "role": "admin", "ip": "127.0.0.1"},
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.delete(f"/eval/golden/cases/{uuid4()}")

    assert resp.status_code == 204


# ============== GET /eval/golden/count ==============
@pytest.mark.asyncio
async def test_count_golden_cases() -> None:
    ds = MagicMock()
    ds.count = AsyncMock(return_value=42)

    app = _make_test_app(dataset_service=ds)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.get("/eval/golden/count")

    assert resp.status_code == 200
    assert resp.json()["total"] == 42


# ============== POST /eval/runs 触发评测 ==============
@pytest.mark.asyncio
async def test_trigger_eval_run_success() -> None:
    run_read = _make_run_read()
    run_obj = MagicMock()
    run_obj.id = run_read.id
    run_obj.run_id = run_read.run_id
    run_obj.prompt_version = run_read.prompt_version
    run_obj.started_at = run_read.started_at
    run_obj.finished_at = run_read.finished_at
    run_obj.total_cases = run_read.total_cases
    run_obj.parse_acc = run_read.parse_acc
    run_obj.retrieval_acc = run_read.retrieval_acc
    run_obj.citation_acc = run_read.citation_acc
    run_obj.risk_kappa = run_read.risk_kappa
    run_obj.report_complete = run_read.report_complete
    run_obj.hallucination_rate = run_read.hallucination_rate
    run_obj.overall_pass = run_read.overall_pass
    run_obj.raw_result_path = run_read.raw_result_path

    runner = MagicMock()
    runner.run = AsyncMock(return_value=run_obj)

    app = _make_test_app(
        eval_runner=runner,
        audit_service=MagicMock(log=AsyncMock()),
        actor={"user_id": "u1", "role": "admin", "ip": "127.0.0.1"},
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.post("/eval/runs", json={
            "prompt_version": "v1.0.0",
        })

    assert resp.status_code == 201
    body = resp.json()
    assert body["prompt_version"] == "v1.0.0"
    assert body["overall_pass"] is True


@pytest.mark.asyncio
async def test_trigger_eval_run_empty_dataset() -> None:
    """评测集为空 → ValidationError → 422。"""
    from app.main import create_app

    runner = MagicMock()
    runner.run = AsyncMock(side_effect=ValidationError("评测集为空"))

    app = create_app()
    async def _get_runner():
        yield runner
    app.dependency_overrides[get_eval_runner] = _get_runner
    app.dependency_overrides[get_audit_service] = lambda: MagicMock(log=AsyncMock())
    app.dependency_overrides[get_actor] = lambda: {
        "user_id": "u1", "role": "admin", "ip": "127.0.0.1",
    }
    async def _get_db_override():
        yield MagicMock()
    app.dependency_overrides[get_db] = _get_db_override

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.post("/api/v1/eval/runs", json={
            "prompt_version": "v1.0.0",
        })

    assert resp.status_code == 422


# ============== GET /eval/runs 列表 ==============
@pytest.mark.asyncio
async def test_list_eval_runs() -> None:
    run_obj = MagicMock()
    run_obj.id = uuid4()
    run_obj.run_id = uuid4()
    run_obj.prompt_version = "v1.0.0"
    run_obj.started_at = datetime.utcnow()
    run_obj.finished_at = datetime.utcnow()
    run_obj.total_cases = 5
    run_obj.parse_acc = 0.95
    run_obj.retrieval_acc = 0.90
    run_obj.citation_acc = 0.85
    run_obj.risk_kappa = 0.90
    run_obj.report_complete = 1.0
    run_obj.hallucination_rate = 0.05
    run_obj.overall_pass = True
    run_obj.raw_result_path = None

    runner = MagicMock()
    runner.list_runs = AsyncMock(return_value=[run_obj])

    app = _make_test_app(eval_runner=runner)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.get("/eval/runs")

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) == 1
    assert body[0]["overall_pass"] is True


# ============== GET /eval/runs/{run_id} ==============
@pytest.mark.asyncio
async def test_get_eval_run_success() -> None:
    run_id = uuid4()
    run_obj = MagicMock()
    run_obj.id = uuid4()
    run_obj.run_id = run_id
    run_obj.prompt_version = "v1.0.0"
    run_obj.started_at = datetime.utcnow()
    run_obj.finished_at = None
    run_obj.total_cases = 3
    run_obj.parse_acc = None
    run_obj.retrieval_acc = None
    run_obj.citation_acc = None
    run_obj.risk_kappa = None
    run_obj.report_complete = None
    run_obj.hallucination_rate = None
    run_obj.overall_pass = None
    run_obj.raw_result_path = None

    runner = MagicMock()
    runner.get_run = AsyncMock(return_value=run_obj)

    app = _make_test_app(eval_runner=runner)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.get(f"/eval/runs/{run_id}")

    assert resp.status_code == 200
    assert resp.json()["run_id"] == str(run_id)
