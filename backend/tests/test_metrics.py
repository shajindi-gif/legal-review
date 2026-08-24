"""指标采集器测试 - Sprint 5 / FR-035 可观测性。

覆盖：
- record_node_latency + snapshot P50/P99
- record_pass_fail + pass_rate 计算
- record_retry + retry_count_avg/max
- record_hallucination + hallucination_rate_avg
- record_task_duration + P50/P99
- 线程安全（并发记录）
- get_metrics_collector 单例
- 空快照
"""
from __future__ import annotations

import threading

import pytest

from app.services.metrics import MetricsCollector, get_metrics_collector


def _fresh_collector() -> MetricsCollector:
    return MetricsCollector()


# ============== record_node_latency ==============
def test_record_node_latency_single() -> None:
    c = _fresh_collector()
    c.record_node_latency("doc_parse", 100)
    snap = c.snapshot()
    assert snap["nodes"]["doc_parse"]["latency_p50"] == 100.0
    assert snap["nodes"]["doc_parse"]["latency_p99"] == 100.0


def test_record_node_latency_multiple() -> None:
    c = _fresh_collector()
    for d in (100, 200, 300, 400, 500):
        c.record_node_latency("doc_parse", d)
    snap = c.snapshot()
    # 5 样本 P50 = 第 2 位（int(5*0.5)=2）→ 300
    # P99 = 第 4 位（int(5*0.99)=4）→ 500
    assert snap["nodes"]["doc_parse"]["latency_p50"] == 300.0
    assert snap["nodes"]["doc_parse"]["latency_p99"] == 500.0


# ============== record_pass_fail ==============
def test_record_pass_fail_pass_rate() -> None:
    c = _fresh_collector()
    for _ in range(8):
        c.record_pass_fail("content_review", True)
    for _ in range(2):
        c.record_pass_fail("content_review", False)
    snap = c.snapshot()
    node = snap["nodes"]["content_review"]
    assert node["pass_count"] == 8
    assert node["fail_count"] == 2
    assert node["pass_rate"] == 0.8


def test_record_pass_fail_no_samples_pass_rate_zero() -> None:
    """无样本 → pass_rate=0。"""
    c = _fresh_collector()
    snap = c.snapshot()
    # 无节点 → 空 dict
    assert snap["nodes"] == {}


# ============== record_retry ==============
def test_record_retry_aggregates() -> None:
    c = _fresh_collector()
    c.record_retry("trace1", 1)
    c.record_retry("trace2", 3)
    c.record_retry("trace3", 5)
    snap = c.snapshot()
    assert snap["retry_count_avg"] == 3.0  # (1+3+5)/3
    assert snap["retry_count_max"] == 5


# ============== record_hallucination ==============
def test_record_hallucination_avg() -> None:
    c = _fresh_collector()
    c.record_hallucination("t1", 0.05)
    c.record_hallucination("t2", 0.10)
    snap = c.snapshot()
    assert snap["hallucination_rate_avg"] == pytest.approx(0.075)


# ============== record_task_duration ==============
def test_record_task_duration() -> None:
    c = _fresh_collector()
    for d in (1000, 2000, 3000, 4000):
        c.record_task_duration(d)
    snap = c.snapshot()
    # 4 样本 P50 = int(4*0.5)=2 → 3000
    assert snap["task_duration_p50"] == 3000.0


# ============== 空快照 ==============
def test_empty_snapshot() -> None:
    c = _fresh_collector()
    snap = c.snapshot()
    assert snap["nodes"] == {}
    assert snap["retry_count_avg"] == 0.0
    assert snap["retry_count_max"] == 0
    assert snap["hallucination_rate_avg"] == 0.0
    assert snap["task_duration_p50"] == 0.0
    assert snap["task_duration_p99"] == 0.0


# ============== 线程安全 ==============
def test_thread_safe_concurrent_writes() -> None:
    """并发 10 线程各记录 100 次 → 无异常。"""
    c = _fresh_collector()

    def worker():
        for i in range(100):
            c.record_node_latency("doc_parse", i)
            c.record_pass_fail("doc_parse", i % 2 == 0)
            c.record_retry(f"t{i}", i)
            c.record_hallucination(f"t{i}", i / 1000)
            c.record_task_duration(i)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    snap = c.snapshot()
    # 10 * 100 = 1000 样本
    assert snap["nodes"]["doc_parse"]["pass_count"] == 500
    assert snap["nodes"]["doc_parse"]["fail_count"] == 500
    assert snap["nodes"]["doc_parse"]["pass_rate"] == 0.5
    assert snap["retry_count_max"] == 99  # 最大重试 99


# ============== 单例 ==============
def test_get_metrics_collector_singleton() -> None:
    """get_metrics_collector 返回同一实例。"""
    c1 = get_metrics_collector()
    c2 = get_metrics_collector()
    assert c1 is c2
