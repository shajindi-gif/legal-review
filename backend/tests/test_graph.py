"""LangGraph 主图测试 - Sprint 4 / FR-018 Supervisor 路由 + Security Harness 强校验。

覆盖：
- build_review_graph：图构建成功 + 节点白名单
- validate_route_table：路由表自检
- classify_router：doc_classify 条件路由
- authority_router：authority_review 条件路由
- evidence_verify_router：Retry Loop + 超限兜底
- SecurityHarness.assert_route_allowed：未注册路由抛错
"""

from __future__ import annotations

import pytest

from app.agent.graph import (
    authority_router,
    build_review_graph,
    classify_router,
    evidence_verify_router,
    supervisor_route,
    validate_route_table,
)
from app.agent.harness import SUPERVISOR_ROUTE_TABLE, SecurityHarness
from app.agent.state import AgentOutput, new_state
from app.core.constants import NodeStatus
from app.core.errors import ValidationError


# ============== 图构建 ==============
def test_build_review_graph_returns_compiled_graph() -> None:
    """build_review_graph 返回 CompiledStateGraph，含全部 11 个节点。"""
    g = build_review_graph()
    assert g is not None
    # langgraph CompiledStateGraph 节点存在 __start__ 和 11 个业务节点
    nodes = list(g.nodes.keys())
    assert "__start__" in nodes
    for expected in (
        "doc_parse", "doc_classify", "legal_retrieve", "authority_review",
        "procedure_review", "content_review", "risk_assessment",
        "evidence_verify", "report_generation", "human_review", "human_fallback",
    ):
        assert expected in nodes, f"missing node: {expected}"


def test_build_review_graph_nodes_all_in_whitelist() -> None:
    """图节点全部在 SecurityHarness.ALLOWED_NODES 白名单内。"""
    g = build_review_graph()
    nodes = list(g.nodes.keys())
    # __start__ / __end__ 是 LangGraph 内部节点，跳过
    biz_nodes = [n for n in nodes if not n.startswith("__")]
    for n in biz_nodes:
        assert n in SecurityHarness.ALLOWED_NODES, f"node={n} 不在白名单"


# ============== 路由表自检 ==============
def test_validate_route_table_passes() -> None:
    """路由表自检返回空问题列表。"""
    issues = validate_route_table()
    assert issues == [], f"route table issues: {issues}"


def test_supervisor_route_table_covers_all_whitelist_nodes() -> None:
    """路由表覆盖所有白名单节点（除 supervisor 自身）。"""
    for node in SecurityHarness.ALLOWED_NODES:
        if node in ("END", "supervisor"):
            continue
        assert node in SUPERVISOR_ROUTE_TABLE, f"route table missing: {node}"


# ============== classify_router ==============
def test_classify_router_normative_to_legal_retrieve() -> None:
    """is_normative=True → legal_retrieve。"""
    state = new_state(task_id="t1", trace_id="t1")
    state["is_normative"] = True
    nxt = classify_router(state)
    assert nxt == "legal_retrieve"


def test_classify_router_non_normative_to_report() -> None:
    """is_normative=False → report_generation。"""
    state = new_state(task_id="t1", trace_id="t1")
    state["is_normative"] = False
    nxt = classify_router(state)
    assert nxt == "report_generation"


def test_classify_router_unauthorized_route_blocked() -> None:
    """classify_router 永远不返回未注册节点（白名单 + 路由表双保险）。"""
    # 直接测 SecurityHarness.assert_route_allowed 对未授权路由抛错
    with pytest.raises(ValidationError):
        SecurityHarness.assert_route_allowed("doc_classify", "authority_review")


# ============== authority_router ==============
def _make_authority_output(status: NodeStatus) -> AgentOutput:
    return AgentOutput(
        agent_name="authority_review",
        node_status=status,
        confidence=0.9,
        raw_json={},
    )


def test_authority_router_pass_to_procedure() -> None:
    """authority_result.node_status=PASS → procedure_review。"""
    state = new_state(task_id="t1", trace_id="t1")
    state["authority_result"] = _make_authority_output(NodeStatus.PASS)
    nxt = authority_router(state)
    assert nxt == "procedure_review"


def test_authority_router_fail_to_report() -> None:
    """authority_result.node_status=FAIL → report_generation。"""
    state = new_state(task_id="t1", trace_id="t1")
    state["authority_result"] = _make_authority_output(NodeStatus.FAIL)
    nxt = authority_router(state)
    assert nxt == "report_generation"


def test_authority_router_retry_to_report() -> None:
    """authority_result.node_status=RETRY → report_generation（不再走程序审查）。"""
    state = new_state(task_id="t1", trace_id="t1")
    state["authority_result"] = _make_authority_output(NodeStatus.RETRY)
    nxt = authority_router(state)
    assert nxt == "report_generation"


def test_authority_router_none_result_to_report() -> None:
    """authority_result=None → 默认走 report_generation（保守路由）。"""
    state = new_state(task_id="t1", trace_id="t1")
    nxt = authority_router(state)
    assert nxt == "report_generation"


# ============== evidence_verify_router ==============
def _make_verify_output(status: NodeStatus) -> AgentOutput:
    return AgentOutput(
        agent_name="evidence_verify",
        node_status=status,
        confidence=0.9,
        raw_json={},
    )


def test_evidence_verify_router_pass_to_report() -> None:
    """verify_result.node_status=PASS → report_generation。"""
    state = new_state(task_id="t1", trace_id="t1")
    state["verify_result"] = _make_verify_output(NodeStatus.PASS)
    nxt = evidence_verify_router(state)
    assert nxt == "report_generation"


def test_evidence_verify_router_fail_within_limit_retries() -> None:
    """verify=FAIL & iteration<max → legal_retrieve（Retry Edge），iteration 自增。"""
    state = new_state(task_id="t1", trace_id="t1")
    state["iteration"] = 1
    state["verify_result"] = _make_verify_output(NodeStatus.FAIL)
    nxt = evidence_verify_router(state)
    assert nxt == "legal_retrieve"
    assert state["iteration"] == 2  # 自增


def test_evidence_verify_router_fail_at_limit_to_fallback() -> None:
    """verify=FAIL & iteration≥max → human_fallback（超限兜底）。"""
    state = new_state(task_id="t1", trace_id="t1")
    state["iteration"] = 5  # = max_iteration
    state["verify_result"] = _make_verify_output(NodeStatus.FAIL)
    nxt = evidence_verify_router(state)
    assert nxt == "human_fallback"
    # 超限不再自增
    assert state["iteration"] == 5


def test_evidence_verify_router_retry_within_limit_retries() -> None:
    """verify=RETRY & iteration<max → legal_retrieve（Retry Edge）。"""
    state = new_state(task_id="t1", trace_id="t1")
    state["iteration"] = 0
    state["verify_result"] = _make_verify_output(NodeStatus.RETRY)
    nxt = evidence_verify_router(state)
    assert nxt == "legal_retrieve"
    assert state["iteration"] == 1


def test_evidence_verify_router_none_result_retries_within_limit() -> None:
    """verify_result=None & iteration<max → legal_retrieve（保守 Retry）。"""
    state = new_state(task_id="t1", trace_id="t1")
    nxt = evidence_verify_router(state)
    assert nxt == "legal_retrieve"


# ============== supervisor_route 入口 ==============
def test_supervisor_route_whitelist_node_passes() -> None:
    """白名单节点通过 supervisor_route 入口校验。"""
    state = new_state(task_id="t1", trace_id="t1")
    # 返回 current 自身（仅做白名单 + 路由表存在性校验）
    assert supervisor_route("doc_parse", state) == "doc_parse"
    assert supervisor_route("evidence_verify", state) == "evidence_verify"


def test_supervisor_route_unregistered_node_rejected() -> None:
    """未在白名单的节点被拒绝。"""
    state = new_state(task_id="t1", trace_id="t1")
    with pytest.raises(ValidationError, match="hidden_node"):
        supervisor_route("hidden_node", state)
