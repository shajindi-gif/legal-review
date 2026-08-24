"""指标 API 测试 - Sprint 5 / FR-035。

策略：直接使用真实 MetricsCollector（无需 mock），测试 /metrics 拉取。
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.v1.metrics import router as metrics_router
from app.services import metrics as metrics_module
from app.services.metrics import MetricsCollector


@pytest.fixture(autouse=True)
def fresh_collector():
    """每个测试用全新 collector。"""
    metrics_module._collector = MetricsCollector()
    yield
    metrics_module._collector = None


def _make_test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(metrics_router)
    return app


# ============== GET /metrics ==============
@pytest.mark.asyncio
async def test_get_metrics_empty() -> None:
    """空指标快照。"""
    app = _make_test_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.get("/metrics")

    assert resp.status_code == 200
    body = resp.json()
    assert body["nodes"] == {}
    assert body["retry_count_avg"] == 0.0
    assert body["retry_count_max"] == 0
    assert body["hallucination_rate_avg"] == 0.0
    assert body["task_duration_p50"] == 0.0


@pytest.mark.asyncio
async def test_get_metrics_with_data() -> None:
    """记录数据后 /metrics 返回聚合指标。"""
    from app.services.metrics import get_metrics_collector

    c = get_metrics_collector()
    c.record_node_latency("doc_parse", 100)
    c.record_pass_fail("doc_parse", True)
    c.record_retry("t1", 2)

    app = _make_test_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.get("/metrics")

    assert resp.status_code == 200
    body = resp.json()
    assert "doc_parse" in body["nodes"]
    assert body["nodes"]["doc_parse"]["latency_p50"] == 100.0
    assert body["nodes"]["doc_parse"]["pass_count"] == 1
    assert body["retry_count_max"] == 2


# ============== GET /metrics/nodes ==============
@pytest.mark.asyncio
async def test_get_node_metrics() -> None:
    from app.services.metrics import get_metrics_collector

    c = get_metrics_collector()
    c.record_node_latency("content_review", 50)
    c.record_pass_fail("content_review", True)

    app = _make_test_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.get("/metrics/nodes")

    assert resp.status_code == 200
    body = resp.json()
    assert "content_review" in body
    assert body["content_review"]["pass_count"] == 1


# ============== POST /metrics/reset ==============
@pytest.mark.asyncio
async def test_reset_metrics() -> None:
    from app.services.metrics import get_metrics_collector

    c = get_metrics_collector()
    c.record_node_latency("x", 100)
    c.record_pass_fail("x", False)

    app = _make_test_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.post("/metrics/reset")

    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    # 重置后快照为空
    snap = get_metrics_collector().snapshot()
    assert snap["nodes"] == {}
