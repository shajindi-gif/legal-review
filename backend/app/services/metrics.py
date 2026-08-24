"""指标采集器 - Sprint 5 / 可观测性。

线程安全的内存指标采集，支持 /metrics API 拉取。
"""

from __future__ import annotations

import threading
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class _NodeStats:
    """单节点统计。"""

    latency_samples: list[int] = field(default_factory=list)
    pass_count: int = 0
    fail_count: int = 0


class MetricsCollector:
    """内存指标采集器 - 线程安全 + snapshot 供 API 拉取。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._node_stats: dict[str, _NodeStats] = defaultdict(_NodeStats)
        self._retry_counts: dict[str, int] = defaultdict(int)
        self._hallucination_samples: list[float] = []
        self._task_durations: list[int] = []

    def record_node_latency(self, agent: str, duration_ms: int) -> None:
        """记录节点延迟。"""
        with self._lock:
            self._node_stats[agent].latency_samples.append(duration_ms)

    def record_pass_fail(self, agent: str, passed: bool) -> None:
        """记录节点通过/失败。"""
        with self._lock:
            if passed:
                self._node_stats[agent].pass_count += 1
            else:
                self._node_stats[agent].fail_count += 1

    def record_retry(self, trace_id: str, count: int) -> None:
        """记录重试次数。"""
        with self._lock:
            self._retry_counts[trace_id] = count

    def record_hallucination(self, trace_id: str, rate: float) -> None:
        """记录幻觉率采样。"""
        with self._lock:
            self._hallucination_samples.append(rate)

    def record_task_duration(self, duration_ms: int) -> None:
        """记录端到端任务时长。"""
        with self._lock:
            self._task_durations.append(duration_ms)

    @staticmethod
    def _percentile(samples: list[int], p: float) -> float:
        """计算百分位数（p=0.5 → P50, p=0.99 → P99）。"""
        if not samples:
            return 0.0
        sorted_samples = sorted(samples)
        idx = int(len(sorted_samples) * p)
        if idx >= len(sorted_samples):
            idx = len(sorted_samples) - 1
        return float(sorted_samples[idx])

    def snapshot(self) -> dict:
        """返回当前指标快照。"""
        with self._lock:
            nodes = {}
            for agent, stats in self._node_stats.items():
                total = stats.pass_count + stats.fail_count
                nodes[agent] = {
                    "latency_p50": self._percentile(stats.latency_samples, 0.5),
                    "latency_p99": self._percentile(stats.latency_samples, 0.99),
                    "pass_count": stats.pass_count,
                    "fail_count": stats.fail_count,
                    "pass_rate": (stats.pass_count / total) if total else 0.0,
                }
            retry_values = list(self._retry_counts.values())
            return {
                "nodes": nodes,
                "retry_count_avg": (
                    sum(retry_values) / len(retry_values) if retry_values else 0.0
                ),
                "retry_count_max": max(retry_values) if retry_values else 0,
                "hallucination_rate_avg": (
                    sum(self._hallucination_samples) / len(self._hallucination_samples)
                    if self._hallucination_samples
                    else 0.0
                ),
                "task_duration_p50": self._percentile(self._task_durations, 0.5),
                "task_duration_p99": self._percentile(self._task_durations, 0.99),
            }


_collector: MetricsCollector | None = None


def get_metrics_collector() -> MetricsCollector:
    """全局单例。"""
    global _collector
    if _collector is None:
        _collector = MetricsCollector()
    return _collector
