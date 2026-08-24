"""Harness 测试 - Evidence / Quality / Security 校验。"""

from __future__ import annotations

import pytest

from app.agent.harness import (
    ContextHarness,
    EvidenceHarness,
    QualityHarness,
    SecurityHarness,
    security_checked,
)
from app.agent.state import AgentOutput, Evidence, ReviewState, RiskItem
from app.core.errors import IterationLimitExceededError, ValidationError


def _make_risk(
    *,
    law_name: str = "行政许可法",
    article: str = "第十五条",
    original_text: str = "原文",
    confidence: float = 0.95,
) -> RiskItem:
    return RiskItem(
        dimension="content",
        risk_type="违法设置行政许可",
        severity="high",
        evidence=Evidence(
            law_name=law_name,
            article=article,
            original_text=original_text,
            explanation="解释",
        ),
        confidence=confidence,
        suggestion="建议",
    )


def test_context_harness_builds_context() -> None:
    state = ReviewState(trace_id="t1", task_id="t1", iteration=0, max_iteration=5)
    ctx = ContextHarness.build_context(state)
    assert ctx["trace_id"] == "t1"
    assert ctx["iteration"] == 0


def test_evidence_harness_passes_with_full_evidence() -> None:
    output = AgentOutput(
        agent_name="authority_review",
        node_status="pass",
        risks=[_make_risk()],
        confidence=0.95,
    )
    missing = EvidenceHarness.validate_output(output)
    assert missing == []


def test_evidence_harness_rejects_missing_law_name() -> None:
    output = AgentOutput(
        agent_name="authority_review",
        node_status="pass",
        risks=[_make_risk(law_name="")],
        confidence=0.95,
    )
    missing = EvidenceHarness.validate_output(output)
    assert any("law_name" in m for m in missing)


def test_evidence_harness_enforce_raises_on_missing() -> None:
    output = AgentOutput(
        agent_name="authority_review",
        node_status="pass",
        risks=[_make_risk(article="")],
        confidence=0.95,
    )
    with pytest.raises(ValidationError):
        EvidenceHarness.enforce(output)


def test_quality_harness_iteration_limit() -> None:
    state = ReviewState(
        trace_id="t1", task_id="t1", iteration=5, max_iteration=5
    )
    with pytest.raises(IterationLimitExceededError):
        QualityHarness.check_iteration(state)


def test_quality_harness_below_limit_passes() -> None:
    state = ReviewState(
        trace_id="t1", task_id="t1", iteration=2, max_iteration=5
    )
    QualityHarness.check_iteration(state)  # 不抛


def test_security_harness_node_allowed() -> None:
    SecurityHarness.assert_node_allowed("doc_parse", ["doc_parse", "doc_classify"])


def test_security_harness_node_blocked() -> None:
    with pytest.raises(ValidationError):
        SecurityHarness.assert_node_allowed("hidden_node", ["doc_parse"])


# ============== Sprint 4 新增：State 不变量 / 路由表 / 装饰器 ==============
def test_security_harness_validate_state_integrity_passes() -> None:
    """完整的 State 通过不变量校验。"""
    state = ReviewState(
        trace_id="t1", task_id="task1", iteration=0,
        max_iteration=5, prompt_versions={},
    )
    SecurityHarness.validate_state_integrity(state)  # 不抛


def test_security_harness_validate_state_integrity_missing_trace_id() -> None:
    """缺 trace_id 抛 ValidationError。"""
    state = ReviewState(task_id="task1", iteration=0, max_iteration=5, prompt_versions={})
    with pytest.raises(ValidationError, match="trace_id"):
        SecurityHarness.validate_state_integrity(state)


def test_security_harness_validate_state_integrity_missing_task_id() -> None:
    """缺 task_id 抛 ValidationError。"""
    state = ReviewState(trace_id="t1", iteration=0, max_iteration=5, prompt_versions={})
    with pytest.raises(ValidationError, match="task_id"):
        SecurityHarness.validate_state_integrity(state)


def test_security_harness_validate_state_integrity_missing_iteration() -> None:
    """缺 iteration 抛 ValidationError。"""
    state = ReviewState(trace_id="t1", task_id="task1", max_iteration=5, prompt_versions={})
    with pytest.raises(ValidationError, match="iteration"):
        SecurityHarness.validate_state_integrity(state)


def test_security_harness_validate_state_integrity_missing_prompt_versions() -> None:
    """缺 prompt_versions 抛 ValidationError。"""
    state = ReviewState(trace_id="t1", task_id="task1", iteration=0, max_iteration=5)
    with pytest.raises(ValidationError, match="prompt_versions"):
        SecurityHarness.validate_state_integrity(state)


# ============== Supervisor 强制路由表 ==============
def test_security_harness_route_allowed_passes() -> None:
    """命中路由表的路由通过。"""
    SecurityHarness.assert_route_allowed("doc_parse", "doc_classify")
    SecurityHarness.assert_route_allowed("doc_classify", "legal_retrieve")
    SecurityHarness.assert_route_allowed("doc_classify", "report_generation")
    SecurityHarness.assert_route_allowed("evidence_verify", "report_generation")
    SecurityHarness.assert_route_allowed("evidence_verify", "legal_retrieve")
    SecurityHarness.assert_route_allowed("evidence_verify", "human_fallback")
    SecurityHarness.assert_route_allowed("human_review", "END")


def test_security_harness_route_blocked_unregistered_current() -> None:
    """current 未在路由表注册抛错。"""
    with pytest.raises(ValidationError, match="未注册"):
        SecurityHarness.assert_route_allowed("unknown_node", "doc_classify")


def test_security_harness_route_blocked_unauthorized_next() -> None:
    """current→next 未命中允许集合抛错（安全节点不可绕过）。"""
    # doc_parse 只能 → doc_classify，不能直接跳到 authority_review
    with pytest.raises(ValidationError, match="不在允许集合"):
        SecurityHarness.assert_route_allowed("doc_parse", "authority_review")
    # procedure_review 只能 → content_review
    with pytest.raises(ValidationError, match="不在允许集合"):
        SecurityHarness.assert_route_allowed("procedure_review", "report_generation")
    # report_generation 只能 → human_review
    with pytest.raises(ValidationError, match="不在允许集合"):
        SecurityHarness.assert_route_allowed("report_generation", "END")


def test_security_harness_audit_log_does_not_raise(caplog) -> None:
    """audit_log 不抛错（仅写日志）。"""
    SecurityHarness.audit_log(
        node="doc_parse", action="enter", trace_id="t1",
        extra={"iteration": 0},
    )


# ============== security_checked 装饰器 ==============
@pytest.mark.asyncio
async def test_security_checked_decorator_passes_valid_state() -> None:
    """完整 State 通过装饰器，节点正常执行。"""
    @security_checked("doc_parse")
    async def fake_node(state: ReviewState) -> ReviewState:
        state["finished"] = True
        return state

    state = ReviewState(
        trace_id="t1", task_id="task1", iteration=0,
        max_iteration=5, prompt_versions={},
    )
    result = await fake_node(state)
    assert result.get("finished") is True


@pytest.mark.asyncio
async def test_security_checked_decorator_rejects_invalid_state() -> None:
    """缺字段的 State 在装饰器入口被拒（抛 ValidationError）。"""
    @security_checked("doc_parse")
    async def fake_node(state: ReviewState) -> ReviewState:
        return state

    # 缺 prompt_versions
    state = ReviewState(trace_id="t1", task_id="task1", iteration=0, max_iteration=5)
    with pytest.raises(ValidationError, match="prompt_versions"):
        await fake_node(state)


@pytest.mark.asyncio
async def test_security_checked_decorator_rejects_unregistered_node() -> None:
    """未在白名单的节点名被装饰器入口拒绝。"""
    @security_checked("hidden_node")
    async def fake_node(state: ReviewState) -> ReviewState:
        return state

    state = ReviewState(
        trace_id="t1", task_id="task1", iteration=0,
        max_iteration=5, prompt_versions={},
    )
    with pytest.raises(ValidationError, match="hidden_node"):
        await fake_node(state)


@pytest.mark.asyncio
async def test_security_checked_decorator_propagates_node_exception() -> None:
    """节点本体抛错时，装饰器不吞错，原异常向上抛。"""
    @security_checked("doc_parse")
    async def fake_node(state: ReviewState) -> ReviewState:
        raise RuntimeError("node exploded")

    state = ReviewState(
        trace_id="t1", task_id="task1", iteration=0,
        max_iteration=5, prompt_versions={},
    )
    with pytest.raises(RuntimeError, match="node exploded"):
        await fake_node(state)


# ============== EvidenceHarness.enforce_silent（Sprint 4 新增） ==============
def test_evidence_harness_enforce_silent_no_missing() -> None:
    """完整证据 → 返回空 missing 列表。"""
    output = AgentOutput(
        agent_name="authority_review",
        node_status="pass",
        risks=[_make_risk()],
        confidence=0.95,
    )
    _, missing = EvidenceHarness.enforce_silent(output)
    assert missing == []


def test_evidence_harness_enforce_silent_returns_missing() -> None:
    """缺证据 → 返回 missing 列表但不抛错（供 evidence_verify_node 内部决策）。"""
    output = AgentOutput(
        agent_name="authority_review",
        node_status="pass",
        risks=[_make_risk(law_name="", article="")],
        confidence=0.95,
    )
    _, missing = EvidenceHarness.enforce_silent(output)
    assert any("law_name" in m for m in missing)
    assert any("article" in m for m in missing)


def test_evidence_harness_enforce_silent_no_risks_passes() -> None:
    """无 risks（如 doc_classify） → 直接通过。"""
    output = AgentOutput(
        agent_name="doc_classify",
        node_status="pass",
        risks=[],
        confidence=0.95,
    )
    _, missing = EvidenceHarness.enforce_silent(output)
    assert missing == []
