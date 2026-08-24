"""LangGraph 主图 - Sprint 4 完整实现（两层 Graph 骨架 + Security Harness 强校验）。

拓扑（来自 04_AGENT_GRAPH_DESIGN.md 第 2 节）：

    START
      │
      ▼
   [doc_parse] ──► [doc_classify]
                       │
            ┌──────────┴──────────┐
            ▼ is_normative=False  ▼ is_normative=True
    [report: 非规范性文件]         [legal_retrieve]
                                   │
                                   ▼
                          [authority_review]
                                   │
                       ┌───────────┴───────────┐
                       ▼ authority=FAIL         ▼ authority=PASS
                [report: 主体不合法]    [procedure_review]
                                          │
                                          ▼
                                  [content_review]
                                          │
                                          ▼
                                  [risk_assessment]
                                          │
                                          ▼
                                  [evidence_verify] ◄─── Retry Edge (iteration < MAX)
                                          │
                              ┌──────────┴──────────┐
                              ▼ verify=PASS           ▼ verify=FAIL & 超限
                        [report_generation]      [human_fallback]
                              │                       │
                              ▼                       ▼
                              [human_review] ◄─────────┘
                                          │
                                          ▼
                                        END

硬约束：
- 每个节点入口走 SecurityHarness.validate_state_integrity + assert_node_allowed
- 每个路由走 SecurityHarness.assert_route_allowed（强制路由表）
- evidence_verify Retry 触发 iteration 自增，超 max_iteration 转 human_fallback
- 安全节点不可绕过：未注册节点 / 未注册路由 立即抛 ValidationError
"""

from __future__ import annotations

from typing import Any

from app.agent.harness import SUPERVISOR_ROUTE_TABLE, SecurityHarness, security_checked
from app.agent.state import ReviewState
from app.core.errors import ValidationError
from app.core.logging import get_logger

logger = get_logger("agent.graph")


# ============== 节点导入 + Security Harness 包装 ==============
# 硬约束：每个节点必须经过 security_checked 装饰器
def _wrap_nodes() -> dict[str, Any]:
    """导入所有节点并用 security_checked 装饰器包装。

    返回 {node_name: wrapped_async_fn}。
    """
    from app.agent.nodes import (
        authority_review_node,
        content_review_node,
        doc_classify_node,
        doc_parse_node,
        evidence_verify_node,
        human_fallback_node,
        human_review_node,
        legal_retrieve_node,
        procedure_review_node,
        report_generation_node,
        risk_assessment_node,
    )

    return {
        "doc_parse": security_checked("doc_parse")(doc_parse_node),
        "doc_classify": security_checked("doc_classify")(doc_classify_node),
        "legal_retrieve": security_checked("legal_retrieve")(legal_retrieve_node),
        "authority_review": security_checked("authority_review")(authority_review_node),
        "procedure_review": security_checked("procedure_review")(procedure_review_node),
        "content_review": security_checked("content_review")(content_review_node),
        "risk_assessment": security_checked("risk_assessment")(risk_assessment_node),
        "evidence_verify": security_checked("evidence_verify")(evidence_verify_node),
        "report_generation": security_checked("report_generation")(report_generation_node),
        "human_review": security_checked("human_review")(human_review_node),
        "human_fallback": security_checked("human_fallback")(human_fallback_node),
    }


# ============== 路由决策函数 ==============
def classify_router(state: ReviewState) -> str:
    """doc_classify → legal_retrieve | report_generation。

    决策：state.is_normative
    """
    current = "doc_classify"
    nxt = "legal_retrieve" if state.get("is_normative") else "report_generation"
    # 硬约束：Supervisor 强制路由表校验
    SecurityHarness.assert_route_allowed(current, nxt)
    SecurityHarness.audit_log(
        node=current, action="route", trace_id=state.get("trace_id"),
        extra={"next": nxt, "is_normative": state.get("is_normative")},
    )
    return nxt


def authority_router(state: ReviewState) -> str:
    """authority_review → procedure_review | report_generation。

    决策：authority_result.node_status
    - PASS → procedure_review
    - FAIL/RETRY → report_generation（主体不合法，直接出报告）
    """
    current = "authority_review"
    auth = state.get("authority_result")
    # node_status 在 _run_llm_node 中映射为 "pass"/"fail"/"retry"
    if auth is not None and auth.node_status == "pass":
        nxt = "procedure_review"
    else:
        nxt = "report_generation"
    SecurityHarness.assert_route_allowed(current, nxt)
    SecurityHarness.audit_log(
        node=current, action="route", trace_id=state.get("trace_id"),
        extra={"next": nxt, "authority_status": auth.node_status if auth else None},
    )
    return nxt


def evidence_verify_router(state: ReviewState) -> str:
    """evidence_verify → report_generation | legal_retrieve (Retry) | human_fallback。

    决策：
    - verify_result.node_status=PASS → report_generation
    - verify_result.node_status≠PASS & iteration<max → legal_retrieve（Retry，iteration 自增）
    - verify_result.node_status≠PASS & iteration≥max → human_fallback

    硬约束：iteration 自增在此处完成（Sprint 4 简化，Sprint 5 重构为独立节点）。
    """
    current = "evidence_verify"
    verify = state.get("verify_result")
    iteration = state.get("iteration", 0)
    max_iter = state.get("max_iteration", 5)

    if verify is not None and verify.node_status == "pass":
        nxt = "report_generation"
    else:
        if iteration < max_iter:
            # 自增 iteration（Sprint 5 移到独立 increment_iteration 节点）
            state["iteration"] = iteration + 1
            nxt = "legal_retrieve"
            logger.info(
                "evidence_retry",
                trace_id=state.get("trace_id"),
                iteration=state["iteration"],
                max_iteration=max_iter,
            )
        else:
            nxt = "human_fallback"

    SecurityHarness.assert_route_allowed(current, nxt)
    SecurityHarness.audit_log(
        node=current, action="route", trace_id=state.get("trace_id"),
        extra={
            "next": nxt,
            "verify_status": verify.node_status if verify else None,
            "iteration": state.get("iteration", 0),
            "max_iteration": max_iter,
        },
    )
    return nxt


# ============== 主图装配 ==============
def build_review_graph() -> Any:
    """构造 LangGraph 主控图（Sprint 4 完整版）。

    装配：
    1. 11 个节点（doc_parse → human_fallback）
    2. 直连边 + 3 个条件路由（classify / authority / evidence_verify）
    3. set_entry_point("doc_parse")
    4. human_review → END

    硬约束：
    - 所有节点经 security_checked 装饰
    - 所有路由经 SecurityHarness.assert_route_allowed
    - 未注册节点 / 未注册路由立即抛 ValidationError

    Returns:
        CompiledGraph（可调 .ainvoke(state) / .astream(state)）
    """
    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError as e:
        logger.error("langgraph_not_installed", error=str(e))
        raise

    wrapped = _wrap_nodes()
    g: StateGraph = StateGraph(ReviewState)

    # 1. 注册所有节点
    for name, fn in wrapped.items():
        g.add_node(name, fn)

    # 2. 装配边
    # 入口
    g.add_edge(START, "doc_parse")

    # doc_parse → doc_classify（固定）
    g.add_edge("doc_parse", "doc_classify")

    # doc_classify 条件路由
    g.add_conditional_edges(
        "doc_classify",
        classify_router,
        {
            "legal_retrieve": "legal_retrieve",
            "report_generation": "report_generation",
        },
    )

    # legal_retrieve → authority_review（固定）
    g.add_edge("legal_retrieve", "authority_review")

    # authority_review 条件路由
    g.add_conditional_edges(
        "authority_review",
        authority_router,
        {
            "procedure_review": "procedure_review",
            "report_generation": "report_generation",
        },
    )

    # procedure_review → content_review → risk_assessment → evidence_verify（固定链）
    g.add_edge("procedure_review", "content_review")
    g.add_edge("content_review", "risk_assessment")
    g.add_edge("risk_assessment", "evidence_verify")

    # evidence_verify 条件路由（含 Retry Loop）
    g.add_conditional_edges(
        "evidence_verify",
        evidence_verify_router,
        {
            "report_generation": "report_generation",
            "legal_retrieve": "legal_retrieve",  # Retry Edge
            "human_fallback": "human_fallback",
        },
    )

    # report_generation → human_review（固定）
    g.add_edge("report_generation", "human_review")

    # human_fallback → human_review（固定）
    g.add_edge("human_fallback", "human_review")

    # human_review → END（固定，终态）
    g.add_edge("human_review", END)

    # 3. 编译
    compiled = g.compile()
    logger.info(
        "graph_built",
        nodes=list(wrapped.keys()),
        entry_point="doc_parse",
        end_node="human_review",
    )
    return compiled


# ============== Stub Graph（fallback，未装 langgraph 时用） ==============
class _StubGraph:
    """Sprint 2 stub - 仅支持 doc_parse 单节点（已废弃，保留兼容）。"""

    async def invoke(self, state: ReviewState) -> ReviewState:
        from app.agent.nodes import doc_parse_node

        wrapped = security_checked("doc_parse")(doc_parse_node)
        return await wrapped(state)


# ============== 工厂 ==============
_graph: Any | None = None


def get_review_graph() -> Any:
    """获取全局 CompiledGraph 单例。"""
    global _graph
    if _graph is None:
        _graph = build_review_graph()
    return _graph


def reset_review_graph() -> None:
    """重置单例（测试用）。"""
    global _graph
    _graph = None


# ============== 路由表自检 ==============
def validate_route_table() -> list[str]:
    """启动时自检：路由表所有节点必须在白名单内。

    Returns:
        问题列表（空表示通过）。
    """
    issues: list[str] = []
    for current, allowed_next in SUPERVISOR_ROUTE_TABLE.items():
        if current != "supervisor" and current not in SecurityHarness.ALLOWED_NODES:
            issues.append(f"route_table: current={current} 不在节点白名单内")
        for nxt in allowed_next:
            if nxt != "END" and nxt not in SecurityHarness.ALLOWED_NODES:
                issues.append(f"route_table: {current}→{nxt} 中 nxt 不在白名单内")
    return issues


# ============== Supervisor 路由决策入口（供外部 API 调用） ==============
def supervisor_route(current: str, state: ReviewState) -> str:
    """Supervisor 路由决策入口（用于 LangGraph 外的精确路由查询）。

    硬约束：current 必须在 SUPERVISOR_ROUTE_TABLE 中，且返回值必须命中允许集合。
    """
    # 硬约束 1：current 必须是白名单节点
    SecurityHarness.assert_node_allowed(current)

    # 硬约束 2：路由必须命中表
    # （具体下一节点由具体 router 决定，此处仅做白名单 + 路由表存在性校验）
    if current not in SUPERVISOR_ROUTE_TABLE:
        raise ValidationError(f"supervisor_route: current={current} 未注册路由表")

    return current
