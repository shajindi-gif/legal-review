"""Harness 控制层 - 四类约束 Agent 行为。

来自 02_SYSTEM_ARCHITECTURE.md 第 3 节 + 04_AGENT_GRAPH_DESIGN.md 第 4 节。
Sprint 4：Context Harness + Security Harness（完整强校验）+ Evidence Harness + Quality Harness。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, Literal

from app.agent.state import AgentOutput, ReviewState
from app.core.config import get_settings
from app.core.errors import IterationLimitExceededError, ValidationError
from app.core.logging import get_logger

logger = get_logger("agent.harness")
settings = get_settings()


# ============== 1. Context Harness ==============
class ContextHarness:
    """上下文管理 - 防止模型遗忘。

    每 Node 输入前注入 Context Window。
    超长上下文采用"分段摘要 + 原文锚点"策略。
    """

    @staticmethod
    def build_context(state: ReviewState) -> dict[str, Any]:
        """构造节点输入上下文。"""
        return {
            "trace_id": state.get("trace_id"),
            "task_id": state.get("task_id"),
            "iteration": state.get("iteration", 0),
            "document_json": state.get("document_json", {}),
            "legal_context": state.get("legal_context", []),
            "user_context": state.get("user_context", {}),
        }


# ============== 2. Evidence Harness ==============
class EvidenceHarness:
    """证据约束 - 所有审核结果必须引用法规条款。

    校验项（来自 04 文档 3.8 节）：
    1. 每个 RiskItem 必含 evidence.law_name
    2. 每个 RiskItem 必含 evidence.article
    3. 每个 RiskItem 必含 evidence.original_text
    4. 引用原文与法规库原文编辑距离 ≤ 阈值（Sprint 5）
    5. confidence ≥ 0.7
    6. 重复风险点合并（Sprint 5）
    """

    @staticmethod
    def validate_output(output: AgentOutput) -> list[str]:
        """校验 Agent 输出，返回缺失项列表。"""
        missing: list[str] = []
        for i, risk in enumerate(output.risks):
            if not risk.evidence.law_name:
                missing.append(f"risk[{i}].evidence.law_name")
            if not risk.evidence.article:
                missing.append(f"risk[{i}].evidence.article")
            if not risk.evidence.original_text:
                missing.append(f"risk[{i}].evidence.original_text")
            if risk.confidence < settings.min_confidence:
                missing.append(f"risk[{i}].confidence<{settings.min_confidence}")
        return missing

    @staticmethod
    def enforce(output: AgentOutput) -> AgentOutput:
        """强制校验：缺失证据则抛 ValidationError（不绕过）。"""
        missing = EvidenceHarness.validate_output(output)
        if missing:
            raise ValidationError(
                f"Evidence Harness 拒绝：{output.agent_name} 缺失证据字段 {missing}"
            )
        return output

    @staticmethod
    def enforce_silent(output: AgentOutput) -> tuple[AgentOutput, list[str]]:
        """软校验：返回 (output, missing)，不抛错（用于 evidence_verify_node 内部决策）。"""
        missing = EvidenceHarness.validate_output(output)
        return output, missing


# ============== 3. Quality Harness ==============
class QualityHarness:
    """质量门控 - Verifier 检查后 PASS/FAIL/Retry。"""

    MAX_ITER: int = settings.max_iteration

    @staticmethod
    def check_iteration(state: ReviewState) -> None:
        """硬约束：迭代超限必须人工兜底。"""
        if state.get("iteration", 0) >= QualityHarness.MAX_ITER:
            raise IterationLimitExceededError(
                agent="supervisor",
                max_iter=QualityHarness.MAX_ITER,
                trace_id=state.get("trace_id"),
            )

    @staticmethod
    def should_retry(state: ReviewState) -> bool:
        """是否还能 retry（iteration < max_iteration）。"""
        return state.get("iteration", 0) < QualityHarness.MAX_ITER


# ============== 4. Security Harness ==============
# 节点白名单（硬约束：未在白名单内的节点禁止路由）
AllowedNode = Literal[
    "doc_parse",
    "doc_classify",
    "legal_retrieve",
    "authority_review",
    "procedure_review",
    "content_review",
    "risk_assessment",
    "evidence_verify",
    "report_generation",
    "human_review",
    "human_fallback",
    "supervisor",
    "END",
]

ALLOWED_NODES: tuple[str, ...] = (
    "doc_parse",
    "doc_classify",
    "legal_retrieve",
    "authority_review",
    "procedure_review",
    "content_review",
    "risk_assessment",
    "evidence_verify",
    "report_generation",
    "human_review",
    "human_fallback",
    "supervisor",
    "END",
)

# Supervisor 强制路由表（current_node → 允许的下一节点集合）
# 硬约束：安全节点不可绕过 - 任何路由必须命中此表
SUPERVISOR_ROUTE_TABLE: dict[str, frozenset[str]] = {
    "doc_parse": frozenset({"doc_classify"}),
    "doc_classify": frozenset({"legal_retrieve", "report_generation"}),
    "legal_retrieve": frozenset({"authority_review"}),
    "authority_review": frozenset({"procedure_review", "report_generation"}),
    "procedure_review": frozenset({"content_review"}),
    "content_review": frozenset({"risk_assessment"}),
    "risk_assessment": frozenset({"evidence_verify"}),
    "evidence_verify": frozenset({"report_generation", "legal_retrieve", "human_fallback"}),
    "report_generation": frozenset({"human_review"}),
    "human_fallback": frozenset({"human_review"}),
    "human_review": frozenset({"END"}),
    "supervisor": frozenset(ALLOWED_NODES),  # supervisor 自身可路由至任意白名单节点
}


class SecurityHarness:
    """安全审计 - 权限/隔离/审计/沙箱。

    与 services.sandbox / services.audit 协同。
    本类仅提供策略接口，实际执行由 service 层完成。

    硬约束（不可绕过）：
    1. 每个节点入口校验 state 不变量（trace_id/iteration/prompt_versions 必填）
    2. 每个节点必须在白名单内
    3. Supervisor 路由必须命中 SUPERVISOR_ROUTE_TABLE
    4. 迭代超限（iteration ≥ max_iteration）必须转 human_fallback
    """

    ALLOWED_NODES: tuple[str, ...] = ALLOWED_NODES

    @staticmethod
    def assert_node_allowed(node: str, allowed_nodes: list[str] | None = None) -> None:
        """安全节点不可绕过：当前节点必须在允许清单内。"""
        pool = allowed_nodes if allowed_nodes is not None else list(ALLOWED_NODES)
        if node not in pool:
            raise ValidationError(
                f"安全节点不可绕过：node={node} not in allowed={pool}"
            )

    @staticmethod
    def validate_state_integrity(state: ReviewState) -> None:
        """State 不变量校验（每节点入口）。"""
        trace_id = state.get("trace_id")
        task_id = state.get("task_id")
        if not trace_id:
            raise ValidationError("State 不变量破坏：trace_id 必填")
        if not task_id:
            raise ValidationError("State 不变量破坏：task_id 必填")
        if "iteration" not in state:
            raise ValidationError("State 不变量破坏：iteration 必填")
        if "max_iteration" not in state:
            raise ValidationError("State 不变量破坏：max_iteration 必填")
        if "prompt_versions" not in state:
            raise ValidationError("State 不变量破坏：prompt_versions 必填")

    @staticmethod
    def assert_route_allowed(current: str, nxt: str) -> None:
        """Supervisor 强制路由表校验。

        硬约束：current → nxt 必须命中 SUPERVISOR_ROUTE_TABLE。
        未命中则抛 ValidationError（安全节点不可绕过）。
        """
        allowed_next = SUPERVISOR_ROUTE_TABLE.get(current)
        if allowed_next is None:
            raise ValidationError(
                f"Supervisor 路由表无 current={current}（未注册节点）"
            )
        if nxt not in allowed_next:
            raise ValidationError(
                f"Supervisor 强制路由拒绝：{current} → {nxt} 不在允许集合 {sorted(allowed_next)}"
            )

    @staticmethod
    def audit_log(
        *,
        node: str,
        action: str,
        trace_id: str | None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """审计日志（每次节点入/出口 + 路由决策）。"""
        logger.info(
            "security_audit",
            node=node,
            action=action,
            trace_id=trace_id,
            **(extra or {}),
        )


def security_checked(
    node_name: str,
) -> Callable[
    [Callable[[ReviewState], Awaitable[ReviewState]]],
    Callable[[ReviewState], Awaitable[ReviewState]],
]:
    """装饰器：包裹 Agent 节点，强制走 Security Harness。

    流程：
    1. 入口 validate_state_integrity（State 不变量）
    2. 入口 assert_node_allowed（节点白名单）
    3. 入口 audit_log（审计）
    4. 执行节点本体
    5. 出口 audit_log（审计）

    异常：节点抛错时记录 audit + error，原异常向上抛（不吞错）。
    """

    def decorator(
        fn: Callable[[ReviewState], Awaitable[ReviewState]],
    ) -> Callable[[ReviewState], Awaitable[ReviewState]]:
        @wraps(fn)
        async def wrapper(state: ReviewState) -> ReviewState:
            trace_id = state.get("trace_id")
            # 1. State 不变量校验
            SecurityHarness.validate_state_integrity(state)
            # 2. 节点白名单校验
            SecurityHarness.assert_node_allowed(node_name)
            # 3. 入口审计
            SecurityHarness.audit_log(
                node=node_name, action="enter", trace_id=trace_id,
                extra={"iteration": state.get("iteration", 0)},
            )
            try:
                result = await fn(state)
            except Exception as e:
                SecurityHarness.audit_log(
                    node=node_name, action="error", trace_id=trace_id,
                    extra={"error": str(e), "error_type": type(e).__name__},
                )
                raise
            # 4. 出口审计
            SecurityHarness.audit_log(
                node=node_name, action="exit", trace_id=trace_id,
            )
            return result

        return wrapper

    return decorator
