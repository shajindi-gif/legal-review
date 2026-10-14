"""可观测性指标 API - Sprint 5 / FR-035。

提供 /metrics 拉取节点延迟、重试次数、幻觉率等运行指标的 JSON 快照，
以及 /metrics/prometheus 输出 Prometheus 文本格式（供 Prometheus 抓取）。
"""
from __future__ import annotations

from fastapi import APIRouter, Response

from app.services.metrics import get_metrics_collector

router = APIRouter(prefix="/metrics", tags=["metrics"])

_PROMETHEUS_MEDIA_TYPE = "text/plain; version=0.0.4; charset=utf-8"


@router.get("")
async def get_metrics() -> dict:
    """拉取当前指标快照（FR-035 可观测性）。

    返回节点级 P50/P99 延迟、通过率、重试均值、幻觉率均值、任务时长。
    """
    return get_metrics_collector().snapshot()


@router.get("/nodes")
async def get_node_metrics() -> dict:
    """节点级指标明细。"""
    nodes: dict = get_metrics_collector().snapshot().get("nodes", {})
    return nodes


@router.get("/prometheus")
async def get_prometheus_metrics() -> Response:
    """输出 Prometheus 文本格式指标（供 Prometheus 抓取）。"""
    return Response(content=render_prometheus(), media_type=_PROMETHEUS_MEDIA_TYPE)


@router.post("/reset")
async def reset_metrics() -> dict:
    """重置全局指标采集器（仅用于测试/排障）。

    生产环境需管理员鉴权后调用。
    """
    import app.services.metrics as m

    m._collector = m.MetricsCollector()
    return {"status": "ok"}


def render_prometheus() -> str:
    """将 MetricsCollector 快照渲染为 Prometheus 文本格式。

    手写 exposition format，避免引入 prometheus_client 依赖；指标为 gauge
    （采集器已自行聚合 P50/P99 等分位数，无需 Histogram 再算）。
    """
    snap = get_metrics_collector().snapshot()

    def esc(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")

    lines: list[str] = [
        "# TYPE legal_review_node_latency_ms_p50 gauge",
        "# TYPE legal_review_node_latency_ms_p99 gauge",
        "# TYPE legal_review_node_pass_count gauge",
        "# TYPE legal_review_node_fail_count gauge",
        "# TYPE legal_review_node_pass_rate gauge",
        "# TYPE legal_review_retry_count_avg gauge",
        "# TYPE legal_review_retry_count_max gauge",
        "# TYPE legal_review_hallucination_rate_avg gauge",
        "# TYPE legal_review_task_duration_ms_p50 gauge",
        "# TYPE legal_review_task_duration_ms_p99 gauge",
    ]

    for node, stats in snap["nodes"].items():
        label = f'node="{esc(node)}"'
        lines.append(f"legal_review_node_latency_ms_p50{{{label}}} {stats['latency_p50']}")
        lines.append(f"legal_review_node_latency_ms_p99{{{label}}} {stats['latency_p99']}")
        lines.append(f"legal_review_node_pass_count{{{label}}} {stats['pass_count']}")
        lines.append(f"legal_review_node_fail_count{{{label}}} {stats['fail_count']}")
        lines.append(f"legal_review_node_pass_rate{{{label}}} {stats['pass_rate']}")

    lines.append(f"legal_review_retry_count_avg {snap['retry_count_avg']}")
    lines.append(f"legal_review_retry_count_max {snap['retry_count_max']}")
    lines.append(f"legal_review_hallucination_rate_avg {snap['hallucination_rate_avg']}")
    lines.append(f"legal_review_task_duration_ms_p50 {snap['task_duration_p50']}")
    lines.append(f"legal_review_task_duration_ms_p99 {snap['task_duration_p99']}")

    return "\n".join(lines) + "\n"