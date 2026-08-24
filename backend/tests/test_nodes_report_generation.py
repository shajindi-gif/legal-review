"""report_generation_node 测试 - Sprint 4 / 审核意见草稿生成。

覆盖：
- 收集 4 个 Agent 输出的 evidences 传入 LLM
- LLM 成功 → report_result 写入 + node_status=PASS
- LLM 失败 → node_status=RETRY
- 无 Agent 结果（全空）仍正常运行
- prompt_versions 写入 report_generation 版本号
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.agent.nodes import report_generation_node
from app.agent.state import AgentOutput, Evidence, ReviewState
from app.core.constants import NodeStatus
from app.core.errors import AgentError


# ============== helpers ==============
def _make_evidence(
    *, law_name: str = "行政许可法", article: str = "第十五条",
) -> Evidence:
    return Evidence(
        law_name=law_name,
        article=article,
        original_text="设定行政许可应当由法定机关。",
        explanation="该文件越权设置行政许可。",
    )


def _make_agent_output(
    *, agent_name: str, evidences: list[Evidence] | None = None,
) -> AgentOutput:
    return AgentOutput(
        agent_name=agent_name,
        node_status=NodeStatus.PASS,
        evidences=evidences or [],
        confidence=0.9,
    )


def _make_state(
    *,
    authority: AgentOutput | None = None,
    procedure: AgentOutput | None = None,
    content: AgentOutput | None = None,
    risk: AgentOutput | None = None,
    document_json: dict[str, Any] | None = None,
) -> ReviewState:
    return ReviewState(
        task_id=str(uuid4()),
        trace_id=str(uuid4()),
        iteration=0,
        max_iteration=5,
        prompt_versions={},
        document_json=document_json or {
            "title": "关于促进中小企业发展的若干意见",
            "issuing_authority": "XX县人民政府",
            "publish_date": "2026-01-01",
            "doc_number": "X政发〔2026〕1号",
        },
        legal_context=[],
        user_context={},
        parse_result=None,
        classify_result=None,
        retrieval_result=None,
        authority_result=authority,
        procedure_result=procedure,
        content_result=content,
        risk_result=risk,
        verify_result=None,
        report_result=None,
        is_normative=True,
        overall_status="pass",
        needs_human_review=False,
        feedback=None,
        finished=False,
        error=None,
    )


def _mock_db_session() -> tuple[AsyncMock, AsyncMock]:
    """构造 mock get_session_factory 返回链（task 查询返回 None 跳过更新）。"""
    mock_session = AsyncMock()
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_session
    mock_cm.__aexit__.return_value = None
    mock_task_result = MagicMock()
    mock_task_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_task_result)
    return mock_cm, mock_session


def _mock_llm_provider(
    *, json_response: dict[str, Any] | None = None,
    raise_error: Exception | None = None,
) -> MagicMock:
    """构造 mock LLM provider。"""
    mock_provider = MagicMock()
    if raise_error is not None:
        mock_provider.complete_json = AsyncMock(side_effect=raise_error)
    else:
        mock_provider.complete_json = AsyncMock(
            return_value=json_response or {
                "report_markdown": "# 审查报告\n...",
                "evidence_count": 2,
                "section_complete": True,
                "confidence": 0.95,
            },
        )
    return mock_provider


# ============== 测试 ==============
@pytest.mark.asyncio
async def test_report_generation_collects_evidences_and_writes_result() -> None:
    """LLM 成功 → report_result 写入 + node_status=PASS。"""
    state = _make_state(
        authority=_make_agent_output(
            agent_name="authority_review",
            evidences=[_make_evidence(law_name="立法法", article="第八条")],
        ),
        procedure=_make_agent_output(
            agent_name="procedure_review",
            evidences=[_make_evidence(law_name="行政许可法", article="第十五条")],
        ),
        content=None,
        risk=None,
    )

    mock_cm, _ = _mock_db_session()
    mock_provider = _mock_llm_provider()

    with (
        patch("app.agent.nodes.get_session_factory") as mock_factory,
        patch("app.agent.nodes.get_llm_provider", return_value=mock_provider),
    ):
        mock_factory.return_value.return_value = mock_cm
        result = await report_generation_node(state)

    report = result.get("report_result")
    assert report is not None
    assert report.agent_name == "report_generation"
    assert report.node_status == NodeStatus.PASS
    assert report.confidence == 0.95
    # LLM 被调用
    mock_provider.complete_json.assert_awaited_once()
    # prompt_versions 写入版本号
    assert "report_generation" in result.get("prompt_versions", {})


@pytest.mark.asyncio
async def test_report_generation_llm_failure_sets_retry() -> None:
    """LLM 异常 → node_status=RETRY，error 写入 raw_json。"""
    state = _make_state()

    mock_cm, _ = _mock_db_session()
    mock_provider = _mock_llm_provider(
        raise_error=AgentError("report_generation", "LLM gateway timeout"),
    )

    with (
        patch("app.agent.nodes.get_session_factory") as mock_factory,
        patch("app.agent.nodes.get_llm_provider", return_value=mock_provider),
    ):
        mock_factory.return_value.return_value = mock_cm
        result = await report_generation_node(state)

    report = result.get("report_result")
    assert report is not None
    assert report.node_status == NodeStatus.RETRY
    assert report.confidence == 0.0
    assert "LLM gateway timeout" in report.raw_json.get("error", "")


@pytest.mark.asyncio
async def test_report_generation_no_agent_results_still_runs() -> None:
    """无任何 Agent 结果（全空）仍正常生成报告。"""
    state = _make_state()  # 全部 None

    mock_cm, _ = _mock_db_session()
    mock_provider = _mock_llm_provider()

    with (
        patch("app.agent.nodes.get_session_factory") as mock_factory,
        patch("app.agent.nodes.get_llm_provider", return_value=mock_provider),
    ):
        mock_factory.return_value.return_value = mock_cm
        result = await report_generation_node(state)

    report = result.get("report_result")
    assert report is not None
    assert report.node_status == NodeStatus.PASS


@pytest.mark.asyncio
async def test_report_generation_passes_all_four_results_to_prompt() -> None:
    """验证 4 个 Agent 输出均传入 Prompt 变量。"""
    state = _make_state(
        authority=_make_agent_output(
            agent_name="authority_review",
            evidences=[_make_evidence(law_name="立法法")],
        ),
        procedure=_make_agent_output(agent_name="procedure_review"),
        content=_make_agent_output(agent_name="content_review"),
        risk=_make_agent_output(agent_name="risk_assessment"),
    )

    mock_cm, _ = _mock_db_session()
    mock_provider = _mock_llm_provider()

    with (
        patch("app.agent.nodes.get_session_factory") as mock_factory,
        patch("app.agent.nodes.get_llm_provider", return_value=mock_provider),
    ):
        mock_factory.return_value.return_value = mock_cm
        await report_generation_node(state)

    # 验证 LLM 被调用，prompt 含全部 4 个结果 JSON
    call_args = mock_provider.complete_json.call_args
    prompt_text = call_args.kwargs.get("prompt") or call_args.args[0]
    assert "立法法" in prompt_text  # authority evidence
    assert "authority_review" in prompt_text
    assert "procedure_review" in prompt_text
    assert "content_review" in prompt_text
    assert "risk_assessment" in prompt_text
