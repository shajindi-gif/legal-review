"""可观测性指标 API - Sprint 5 / FR-035。

提供 /metrics 拉取节点延迟、重试次数、幻觉率等运行指标。
"""
from __future__ import annotations

from fastapi import APIRouter

from app.services.metrics import get_metrics_collector

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("")
async def get_metrics() -> dict:
    """拉取当前指标快照（FR-035 可观测性）。

    返回节点级 P50/P99 延迟、通过率、重试均值、幻觉率均值、任务时长。
    """
    return get_metrics_collector().snapshot()


@router.get("/nodes")
async def get_node_metrics() -> dict:
    """节点级指标明细。"""
    return get_metrics_collector().snapshot().get("nodes", {})


@router.post("/reset")
async def reset_metrics() -> dict:
    """重置全局指标采集器（仅用于测试/排障）。

    生产环境需管理员鉴权后调用。
    """
    import app.services.metrics as m

    m._collector = m.MetricsCollector()
    return {"status": "ok"}
