"""反馈 API 测试 - Sprint 5 / FR-032。

策略：用独立 FastAPI app 只挂 feedback router，通过 dependency_overrides 注入 mock。
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
from app.api.v1.feedback import get_feedback_service
from app.api.v1.feedback import router as feedback_router
from app.core.errors import NotFoundError, ValidationError


def _make_test_app(
    *,
    feedback_service: Any = None,
    audit_service: Any = None,
    actor: dict | None = None,
) -> FastAPI:
    app = FastAPI()
    app.include_router(feedback_router)

    if feedback_service is not None:
        async def _get_fb():
            yield feedback_service
        app.dependency_overrides[get_feedback_service] = _get_fb
    if audit_service is not None:
        app.dependency_overrides[get_audit_service] = lambda: audit_service
    if actor is not None:
        app.dependency_overrides[get_actor] = lambda: actor

    async def _get_db_override():
        yield MagicMock()
    app.dependency_overrides[get_db] = _get_db_override

    return app


def _make_case_mock(**overrides) -> MagicMock:
    defaults = {
        "id": uuid4(),
        "task_id": uuid4(),
        "reviewer_id": uuid4(),
        "agent_name": "content_review",
        "section": "四、发现问题",
        "ai_output": {"risk": "low"},
        "human_modified": {"risk": "high"},
        "modify_reason": "风险判断错误",
        "reason_category": "risk_misjudged",
        "incorporated": False,
        "prompt_version_after": None,
        "created_at": datetime.utcnow(),
    }
    defaults.update(overrides)
    m = MagicMock()
    for k, v in defaults.items():
        setattr(m, k, v)
    return m


# ============== POST /feedback/tasks/{task_id} 提交反馈 ==============
@pytest.mark.asyncio
async def test_submit_feedback_success() -> None:
    case = _make_case_mock()
    svc = MagicMock()
    svc.record = AsyncMock(return_value=case)

    app = _make_test_app(
        feedback_service=svc,
        audit_service=MagicMock(log=AsyncMock()),
        actor={"user_id": str(case.reviewer_id), "role": "reviewer", "ip": "127.0.0.1"},
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.post(f"/feedback/tasks/{case.task_id}", json={
            "agent_name": "content_review",
            "section": "四、发现问题",
            "ai_output": {"risk": "low"},
            "human_modified": {"risk": "high"},
            "modify_reason": "风险判断错误",
            "reason_category": "risk_misjudged",
        })

    assert resp.status_code == 201
    body = resp.json()
    assert body["agent_name"] == "content_review"
    assert body["incorporated"] is False
    svc.record.assert_awaited()


@pytest.mark.asyncio
async def test_submit_feedback_missing_reviewer_id() -> None:
    """X-User-Id 缺失 → ValidationError → 422。"""
    from app.main import create_app

    svc = MagicMock()
    svc.record = AsyncMock()

    app = create_app()
    async def _get_fb():
        yield svc
    app.dependency_overrides[get_feedback_service] = _get_fb
    app.dependency_overrides[get_audit_service] = lambda: MagicMock(log=AsyncMock())
    app.dependency_overrides[get_actor] = lambda: {
        "user_id": None, "role": "reviewer", "ip": "127.0.0.1",
    }
    async def _get_db_override():
        yield MagicMock()
    app.dependency_overrides[get_db] = _get_db_override

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.post(f"/api/v1/feedback/tasks/{uuid4()}", json={
            "agent_name": "x",
            "ai_output": {"a": 1},
            "human_modified": {"b": 2},
            "modify_reason": "test",
        })

    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"


@pytest.mark.asyncio
async def test_submit_feedback_invalid_reviewer_id() -> None:
    """X-User-Id 非 UUID → ValidationError → 422。"""
    from app.main import create_app

    svc = MagicMock()
    svc.record = AsyncMock()

    app = create_app()
    async def _get_fb():
        yield svc
    app.dependency_overrides[get_feedback_service] = _get_fb
    app.dependency_overrides[get_audit_service] = lambda: MagicMock(log=AsyncMock())
    app.dependency_overrides[get_actor] = lambda: {
        "user_id": "not-a-uuid", "role": "reviewer", "ip": "127.0.0.1",
    }
    async def _get_db_override():
        yield MagicMock()
    app.dependency_overrides[get_db] = _get_db_override

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.post(f"/api/v1/feedback/tasks/{uuid4()}", json={
            "agent_name": "x",
            "ai_output": {"a": 1},
            "human_modified": {"b": 2},
            "modify_reason": "test",
        })

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_submit_feedback_same_output_raises() -> None:
    """ai_output == human_modified → ValidationError → 422。"""
    from app.main import create_app

    svc = MagicMock()
    svc.record = AsyncMock(side_effect=ValidationError("无变化"))

    app = create_app()
    async def _get_fb():
        yield svc
    app.dependency_overrides[get_feedback_service] = _get_fb
    app.dependency_overrides[get_audit_service] = lambda: MagicMock(log=AsyncMock())
    app.dependency_overrides[get_actor] = lambda: {
        "user_id": str(uuid4()), "role": "reviewer", "ip": "127.0.0.1",
    }
    async def _get_db_override():
        yield MagicMock()
    app.dependency_overrides[get_db] = _get_db_override

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.post(f"/api/v1/feedback/tasks/{uuid4()}", json={
            "agent_name": "x",
            "ai_output": {"a": 1},
            "human_modified": {"a": 1},
            "modify_reason": "无变化",
        })

    assert resp.status_code == 422


# ============== GET /feedback/tasks/{task_id} 查询任务反馈 ==============
@pytest.mark.asyncio
async def test_list_task_feedback() -> None:
    case = _make_case_mock()
    svc = MagicMock()
    svc.list_by_task = AsyncMock(return_value=[case])

    app = _make_test_app(feedback_service=svc)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.get(f"/feedback/tasks/{case.task_id}")

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) == 1
    assert body[0]["modify_reason"] == "风险判断错误"


# ============== GET /feedback/unincorporated 未吸收列表 ==============
@pytest.mark.asyncio
async def test_list_unincorporated() -> None:
    cases = [
        _make_case_mock(incorporated=False),
        _make_case_mock(incorporated=False),
    ]
    svc = MagicMock()
    svc.list_unincorporated = AsyncMock(return_value=cases)

    app = _make_test_app(feedback_service=svc)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.get("/feedback/unincorporated")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    assert all(not b["incorporated"] for b in body)


# ============== GET /feedback/batch-review 批次复盘 ==============
@pytest.mark.asyncio
async def test_batch_review() -> None:
    from app.schemas.eval import FeedbackBatchReviewResponse

    result = FeedbackBatchReviewResponse(
        total_cases=3,
        by_category={"risk_misjudged": 2, "citation_wrong": 1},
        top_reasons=[{"reason": "风险判断错误", "count": 2}],
    )
    svc = MagicMock()
    svc.batch_review = AsyncMock(return_value=result)

    app = _make_test_app(feedback_service=svc)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.get("/feedback/batch-review")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total_cases"] == 3
    assert body["by_category"]["risk_misjudged"] == 2


# ============== POST /feedback/cases/{case_id}/incorporate 标记吸收 ==============
@pytest.mark.asyncio
async def test_mark_incorporated_success() -> None:
    case = _make_case_mock(incorporated=True, prompt_version_after="v1.1.0")
    svc = MagicMock()
    svc.mark_incorporated = AsyncMock(return_value=case)

    app = _make_test_app(
        feedback_service=svc,
        audit_service=MagicMock(log=AsyncMock()),
        actor={"user_id": str(case.reviewer_id), "role": "admin", "ip": "127.0.0.1"},
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.post(
            f"/feedback/cases/{case.id}/incorporate",
            params={"prompt_version_after": "v1.1.0"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["incorporated"] is True
    assert body["prompt_version_after"] == "v1.1.0"


@pytest.mark.asyncio
async def test_mark_incorporated_not_found() -> None:
    from app.main import create_app

    svc = MagicMock()
    svc.mark_incorporated = AsyncMock(side_effect=NotFoundError("FeedbackCase", "x"))

    app = create_app()
    async def _get_fb():
        yield svc
    app.dependency_overrides[get_feedback_service] = _get_fb
    app.dependency_overrides[get_audit_service] = lambda: MagicMock(log=AsyncMock())
    app.dependency_overrides[get_actor] = lambda: {
        "user_id": str(uuid4()), "role": "admin", "ip": "127.0.0.1",
    }
    async def _get_db_override():
        yield MagicMock()
    app.dependency_overrides[get_db] = _get_db_override

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.post(
            f"/api/v1/feedback/cases/{uuid4()}/incorporate",
            params={"prompt_version_after": "v1.1.0"},
        )

    assert resp.status_code == 404
