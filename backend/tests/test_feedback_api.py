"""反馈 API 测试 - Sprint 5 / FR-032。

策略：用独立 FastAPI app 只挂 feedback router，通过 dependency_overrides 注入 mock。

鉴权口径（安全整改后）：reviewer 身份来自 JWT 解析出的 CorePrincipal，
不再接受 X-User-Id / X-User-Role 请求头自报身份。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_audit_service, get_current_user, get_db
from app.api.v1.feedback import get_feedback_service
from app.api.v1.feedback import router as feedback_router
from app.core.errors import NotFoundError, ValidationError
from app.services.core_auth_client import CorePrincipal


def _principal(
    *,
    user_id: UUID | None = None,
    role: str = "reviewer",
) -> CorePrincipal:
    return CorePrincipal(
        id=user_id or uuid4(),
        tenant_id=None,
        email="reviewer@example.com",
        full_name="测试审查员",
        role=role,
        is_active=True,
    )


def _make_test_app(
    *,
    feedback_service: Any = None,
    audit_service: Any = None,
    user: CorePrincipal | None = None,
) -> FastAPI:
    app = FastAPI()
    app.include_router(feedback_router)

    if feedback_service is not None:
        async def _get_fb():
            yield feedback_service
        app.dependency_overrides[get_feedback_service] = _get_fb
    if audit_service is not None:
        app.dependency_overrides[get_audit_service] = lambda: audit_service
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user

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
        user=_principal(user_id=case.reviewer_id),
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
    # reviewer_id 必须取自 JWT 主体，而非请求头
    assert svc.record.await_args.kwargs["reviewer_id"] == case.reviewer_id


@pytest.mark.asyncio
async def test_submit_feedback_without_jwt_returns_401() -> None:
    """缺少 Authorization 头 → 401，不再接受 X-User-Id 自报身份。"""
    from app.main import create_app

    svc = MagicMock()
    svc.record = AsyncMock()

    app = create_app()
    async def _get_fb():
        yield svc
    app.dependency_overrides[get_feedback_service] = _get_fb
    app.dependency_overrides[get_audit_service] = lambda: MagicMock(log=AsyncMock())
    async def _get_db_override():
        yield MagicMock()
    app.dependency_overrides[get_db] = _get_db_override

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.post(
            f"/api/v1/feedback/tasks/{uuid4()}",
            headers={"X-User-Id": str(uuid4()), "X-User-Role": "reviewer"},
            json={
                "agent_name": "x",
                "ai_output": {"a": 1},
                "human_modified": {"b": 2},
                "modify_reason": "test",
            },
        )

    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "auth_error"
    svc.record.assert_not_awaited()


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
    app.dependency_overrides[get_current_user] = lambda: _principal()
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
        user=_principal(role="admin"),
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
    app.dependency_overrides[get_current_user] = lambda: _principal(role="admin")
    async def _get_db_override():
        yield MagicMock()
    app.dependency_overrides[get_db] = _get_db_override

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.post(
            f"/api/v1/feedback/cases/{uuid4()}/incorporate",
            params={"prompt_version_after": "v1.1.0"},
        )

    assert resp.status_code == 404
