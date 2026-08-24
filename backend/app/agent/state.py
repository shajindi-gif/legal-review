"""Agent State Schema - LangGraph 全局状态。

来自 04_AGENT_GRAPH_DESIGN.md 第 1 节。
硬约束：trace_id / iteration / max_iteration / prompt_versions 必填。
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict

from pydantic import BaseModel, Field

# ============== 类型别名 ==============
RiskDimension = Literal["authority", "procedure", "content", "prohibition", "interest"]
RiskSeverity = Literal["low", "medium", "high", "critical"]
NodeStatus = Literal["pass", "fail", "retry", "skipped"]
OverallStatus = Literal["pass", "risk", "fail"]


# ============== 证据链 ==============
class Evidence(BaseModel):
    """证据链（每个风险点必须附证据）。"""
    law_name: str = Field(description="法规名称")
    article: str = Field(description="条款号，如 第十五条")
    original_text: str = Field(description="条款原文")
    explanation: str = Field(description="与文件冲突的解释")


class RiskItem(BaseModel):
    """风险点（Evidence Harness 强制约束）。"""
    dimension: RiskDimension
    risk_type: str = Field(description="如 违法设置行政许可")
    severity: RiskSeverity
    evidence: Evidence
    confidence: float = Field(ge=0.0, le=1.0)
    suggestion: str = Field(description="修改建议")


class AgentOutput(BaseModel):
    """Agent 节点统一输出。"""
    agent_name: str
    node_status: NodeStatus
    risks: list[RiskItem] = Field(default_factory=list)
    evidences: list[Evidence] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    raw_json: dict[str, Any] = Field(default_factory=dict)
    duration_ms: int = 0
    iteration: int = 0


# ============== 全局 State ==============
class ReviewState(TypedDict, total=False):
    """LangGraph 全局状态。

    硬约束字段（必填）：
    - trace_id
    - task_id
    - iteration
    - max_iteration
    - prompt_versions
    """

    # === 追踪元数据（硬约束必填）===
    trace_id: str
    task_id: str
    iteration: int
    max_iteration: int  # = 5
    prompt_versions: dict[str, str]

    # === Context Harness ===
    document_json: dict[str, Any]  # 文件解析结构化结果
    legal_context: list[dict[str, Any]]  # 检索召回的条款
    user_context: dict[str, Any]

    # === 各节点输出 ===
    parse_result: AgentOutput | None
    classify_result: AgentOutput | None
    retrieval_result: AgentOutput | None
    authority_result: AgentOutput | None
    procedure_result: AgentOutput | None
    content_result: AgentOutput | None
    risk_result: AgentOutput | None
    verify_result: AgentOutput | None
    report_result: AgentOutput | None

    # === 路由控制 ===
    is_normative: bool | None
    overall_status: OverallStatus
    needs_human_review: bool
    feedback: dict[str, Any] | None

    # === 终态 ===
    finished: bool
    error: str | None


def new_state(task_id: str, trace_id: str) -> ReviewState:
    """构造初始 State。"""
    return ReviewState(
        trace_id=trace_id,
        task_id=task_id,
        iteration=0,
        max_iteration=5,
        prompt_versions={},
        document_json={},
        legal_context=[],
        user_context={},
        parse_result=None,
        classify_result=None,
        retrieval_result=None,
        authority_result=None,
        procedure_result=None,
        content_result=None,
        risk_result=None,
        verify_result=None,
        report_result=None,
        is_normative=None,
        overall_status="pass",
        needs_human_review=False,
        feedback=None,
        finished=False,
        error=None,
    )
