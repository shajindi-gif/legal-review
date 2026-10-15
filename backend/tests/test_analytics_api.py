"""埋点 API HTTP 层测试。

策略：独立 FastAPI app 只挂 analytics router；用 app.dependency_overrides
把 get_db 替换为 FakeSession（仅记录 add 进来的对象，不查真库）。
- 单条写入 → 200 且 accepted=1
- 批量 3 条 → 200 且 accepted=3
- 白名单外事件 → 422
- 无 Authorization 头 → 200 且 user_id 为 None（匿名）
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_db
from app.api.v1.analytics import router as analytics_router


class FakeSession:
    """Fake AsyncSession：只记录 add 的对象，commit/flush 计数，不触库。"""

    def __init__(self) -> None:
        self.added: list[Any] = []
        self.commit_calls = 0

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        self.commit_calls += 1

    async def flush(self) -> None:
        return None


@pytest.fixture
def fake_session() -> FakeSession:
    return FakeSession()


@pytest.fixture
def client_factory(fake_session: FakeSession):
    """构造只挂 analytics router 且 override get_db 的测试客户端工厂。"""

    def _make() -> AsyncClient:
        app = FastAPI()
        app.include_router(analytics_router)

        async def _override_db():
            yield fake_session

        app.dependency_overrides[get_db] = _override_db
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    return _make


async def test_single_event_accepted(client_factory, fake_session) -> None:
    """用例①：单条写入 200 且 accepted=1。"""
    async with client_factory() as client:
        resp = await client.post(
            "/analytics/events",
            json={"event": "page_view", "page": "/pricing", "anonymous_id": "anon-1"},
        )
    assert resp.status_code == 200
    assert resp.json() == {"accepted": 1}
    assert len(fake_session.added) == 1
    assert fake_session.added[0].event == "page_view"
    assert fake_session.added[0].anonymous_id == "anon-1"
    assert fake_session.commit_calls == 1


async def test_batch_events_accepted(client_factory, fake_session) -> None:
    """用例②：批量 3 条 200 且 accepted=3。"""
    async with client_factory() as client:
        resp = await client.post(
            "/analytics/events",
            json={
                "events": [
                    {"event": "page_view"},
                    {"event": "pricing_view"},
                    {"event": "custom_error", "properties": {"msg": "boom"}},
                ]
            },
        )
    assert resp.status_code == 200
    assert resp.json() == {"accepted": 3}
    assert len(fake_session.added) == 3
    assert [e.event for e in fake_session.added] == [
        "page_view",
        "pricing_view",
        "custom_error",
    ]


async def test_event_not_in_whitelist_rejected(client_factory, fake_session) -> None:
    """用例③：白名单外事件 422，且不落库。"""
    async with client_factory() as client:
        resp = await client.post(
            "/analytics/events",
            json={"event": "totally_fake_event"},
        )
    assert resp.status_code == 422
    assert fake_session.added == []


async def test_no_auth_header_anonymous(client_factory, fake_session) -> None:
    """用例④：无 Authorization 头 → 200 且 user_id 为 None。"""
    async with client_factory() as client:
        resp = await client.post(
            "/analytics/events",
            json={"event": "page_view"},
        )
    assert resp.status_code == 200
    assert resp.json() == {"accepted": 1}
    assert len(fake_session.added) == 1
    assert fake_session.added[0].user_id is None
