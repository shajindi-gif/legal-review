"""评测服务层测试 - Sprint 5 / FR-029/031。

覆盖：
- EvalMetrics.overall_pass 阈值判断
- _field_f1 字段 F1
- _retrieval_recall Top-10 召回
- _citation_accuracy 引用准确率
- _cohen_kappa 一致性
- _report_completeness 7 章节完整率
- _hallucination_rate 幻觉率
- compute_case_metrics 综合计算
- EvalRunner.check_gate 门控
- GoldenDatasetService 导入/查询/删除（async session mock）
- EvalRunner.run 框架级（case_runner 注入）
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.constants import GoldenCategory
from app.core.errors import NotFoundError, ValidationError
from app.schemas.eval import GoldenBatchImportResponse, GoldenCaseCreate
from app.services.eval_runner import (
    EvalMetrics,
    EvalRunner,
    GoldenDatasetService,
    _citation_accuracy,
    _cohen_kappa,
    _field_f1,
    _hallucination_rate,
    _report_completeness,
    _retrieval_recall,
    compute_case_metrics,
)


# ============== EvalMetrics ==============
def test_overall_pass_all_meets_threshold() -> None:
    """全部达标 → True。"""
    m = EvalMetrics(
        parse_acc=0.95, retrieval_acc=0.90, citation_acc=0.85,
        risk_kappa=0.90, report_complete=1.0, hallucination_rate=0.05,
    )
    assert m.overall_pass is True


def test_overall_pass_one_fails() -> None:
    """任一指标不达标 → False。"""
    m = EvalMetrics(
        parse_acc=0.94,  # 不达标
        retrieval_acc=0.95, citation_acc=0.90,
        risk_kappa=0.95, report_complete=1.0, hallucination_rate=0.01,
    )
    assert m.overall_pass is False


def test_overall_pass_hallucination_too_high() -> None:
    """幻觉率超标 → False。"""
    m = EvalMetrics(
        parse_acc=1.0, retrieval_acc=1.0, citation_acc=1.0,
        risk_kappa=1.0, report_complete=1.0, hallucination_rate=0.06,
    )
    assert m.overall_pass is False


# ============== _field_f1 ==============
def test_field_f1_perfect_match() -> None:
    assert _field_f1({"a": 1, "b": 2}, {"a": 1, "b": 2}) == 1.0


def test_field_f1_partial_match() -> None:
    f1 = _field_f1({"a": 1, "c": 3}, {"a": 1, "b": 2})
    # precision=1/2=0.5, recall=1/2=0.5, f1=0.5
    assert f1 == pytest.approx(0.5)


def test_field_f1_no_expected() -> None:
    """期望字段为空 → 1.0。"""
    assert _field_f1({"a": 1}, {}) == 1.0


def test_field_f1_no_actual_with_expected() -> None:
    """实际空但期望非空 → 0.0。"""
    assert _field_f1({}, {"a": 1}) == 0.0


# ============== _retrieval_recall ==============
def test_retrieval_recall_all_hit() -> None:
    actual = [{"law_name": "法1", "article": "第一条"}]
    expected = [{"law_name": "法1", "article": "第一条"}]
    assert _retrieval_recall(actual, expected) == 1.0


def test_retrieval_recall_partial_hit() -> None:
    actual = [{"law_name": "法1", "article": "第一条"}]
    expected = [
        {"law_name": "法1", "article": "第一条"},
        {"law_name": "法2", "article": "第二条"},
    ]
    assert _retrieval_recall(actual, expected) == 0.5


def test_retrieval_recall_empty_expected() -> None:
    assert _retrieval_recall([], []) == 1.0


# ============== _citation_accuracy ==============
def test_citation_accuracy_all_correct() -> None:
    actual = [
        {"law_name": "法1", "article": "第一条"},
        {"law_name": "法2", "article": "第二条"},
    ]
    expected = actual
    assert _citation_accuracy(actual, expected) == 1.0


def test_citation_accuracy_partial_correct() -> None:
    actual = [
        {"law_name": "法1", "article": "第一条"},
        {"law_name": "法3", "article": "第三条"},  # 错误引用
    ]
    expected = [
        {"law_name": "法1", "article": "第一条"},
        {"law_name": "法2", "article": "第二条"},
    ]
    assert _citation_accuracy(actual, expected) == 0.5


def test_citation_accuracy_empty_actual_with_expected() -> None:
    assert _citation_accuracy([], [{"x": 1}]) == 0.0


def test_citation_accuracy_empty_both() -> None:
    assert _citation_accuracy([], []) == 1.0


# ============== _cohen_kappa ==============
def test_cohen_kappa_perfect_agreement() -> None:
    pairs = [("pass", "pass"), ("pass", "pass"), ("fail", "fail")]
    assert _cohen_kappa(pairs) == pytest.approx(1.0)


def test_cohen_kappa_empty() -> None:
    assert _cohen_kappa([]) == 0.0


def test_cohen_kappa_all_same_label() -> None:
    """全部同一标签（p_e=1）→ 1.0。"""
    pairs = [("pass", "pass"), ("pass", "pass")]
    assert _cohen_kappa(pairs) == 1.0


def test_cohen_kappa_random_agreement() -> None:
    """观察一致性 = 期望一致性 → kappa ≈ 0。"""
    pairs = [("pass", "pass"), ("fail", "fail"), ("pass", "fail"), ("fail", "pass")]
    # p_o = 0.5, p_e = 0.5 (pass 各占一半) → kappa = 0
    assert _cohen_kappa(pairs) == pytest.approx(0.0, abs=1e-9)


# ============== _report_completeness ==============
def test_report_completeness_full() -> None:
    report = (
        "一、文件基本情况\n二、审查依据\n三、审核过程\n四、发现问题\n"
        "五、风险等级\n六、修改建议\n七、审查意见"
    )
    assert _report_completeness(report) == 1.0


def test_report_completeness_partial() -> None:
    report = "一、文件基本情况\n二、审查依据\n三、审核过程"
    assert _report_completeness(report) == pytest.approx(3 / 7)


def test_report_completeness_empty() -> None:
    assert _report_completeness("") == 0.0


# ============== _hallucination_rate ==============
def test_hallucination_rate_no_evidence() -> None:
    risks = [{"law_name": "", "article": ""}, {"law_name": "法1", "article": "第一条"}]
    assert _hallucination_rate(risks) == 0.5


def test_hallucination_rate_all_have_evidence() -> None:
    risks = [
        {"law_name": "法1", "article": "第一条"},
        {"law_name": "法2", "article": "第二条"},
    ]
    assert _hallucination_rate(risks) == 0.0


def test_hallucination_rate_empty() -> None:
    assert _hallucination_rate([]) == 0.0


# ============== compute_case_metrics ==============
def test_compute_case_metrics_full() -> None:
    actual = {
        "document_json": {"a": 1, "b": 2},
        "legal_context": [{"law_name": "法1", "article": "第一条"}],
        "evidences": [{"law_name": "法1", "article": "第一条"}],
        "overall_status": "pass",
        "report_markdown": (
            "一、文件基本情况\n二、审查依据\n三、审核过程\n四、发现问题\n"
            "五、风险等级\n六、修改建议\n七、审查意见"
        ),
        "risks": [{"law_name": "法1", "article": "第一条"}],
    }
    expected = {
        "document_json": {"a": 1, "b": 2},
        "risks": [{"law_name": "法1", "article": "第一条"}],
        "overall_status": "pass",
    }
    m = compute_case_metrics(actual, expected)
    assert m.parse_acc == 1.0
    assert m.retrieval_acc == 1.0
    assert m.citation_acc == 1.0
    assert m.risk_kappa == 1.0
    assert m.report_complete == 1.0
    assert m.hallucination_rate == 0.0
    assert m.overall_pass is True


def test_compute_case_metrics_mismatch() -> None:
    actual = {
        "document_json": {"a": 1, "c": 3},
        "legal_context": [],
        "evidences": [{"law_name": "法X", "article": "第X条"}],
        "overall_status": "fail",
        "report_markdown": "",
        "risks": [{"law_name": "", "article": ""}],
    }
    expected = {
        "document_json": {"a": 1, "b": 2},
        "risks": [{"law_name": "法1", "article": "第一条"}],
        "overall_status": "pass",
    }
    m = compute_case_metrics(actual, expected)
    assert m.parse_acc < 1.0
    assert m.retrieval_acc < 1.0
    assert m.citation_acc == 0.0  # 无期望命中
    assert m.risk_kappa == 0.0
    assert m.report_complete == 0.0
    assert m.hallucination_rate == 1.0
    assert m.overall_pass is False


# ============== EvalRunner.check_gate ==============
def test_check_gate_pass() -> None:
    m = EvalMetrics(
        parse_acc=0.95, retrieval_acc=0.90, citation_acc=0.85,
        risk_kappa=0.90, report_complete=1.0, hallucination_rate=0.05,
    )
    assert EvalRunner.check_gate(m) is True


def test_check_gate_fail() -> None:
    m = EvalMetrics(
        parse_acc=0.94, retrieval_acc=0.90, citation_acc=0.85,
        risk_kappa=0.90, report_complete=1.0, hallucination_rate=0.05,
    )
    assert EvalRunner.check_gate(m) is False


# ============== GoldenDatasetService ==============
@pytest.mark.asyncio
async def test_golden_batch_import_success() -> None:
    """批量导入成功。"""
    session = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()

    svc = GoldenDatasetService(session)
    cases = [
        GoldenCaseCreate(
            case_name="case1",
            category=GoldenCategory.NORMAL,
            input_file_path="/tmp/case1.txt",
            expected_json={"x": 1},
            expected_status="pass",
        ),
        GoldenCaseCreate(
            case_name="case2",
            category=GoldenCategory.AUTHORITY_VIOLATION,
            input_file_path="/tmp/case2.txt",
            expected_json={"y": 2},
            expected_status="fail",
        ),
    ]
    result = await svc.batch_import(cases)
    assert isinstance(result, GoldenBatchImportResponse)
    assert result.total == 2
    assert result.success == 2
    assert result.failed == 0
    assert session.commit.await_count == 1


@pytest.mark.asyncio
async def test_golden_batch_import_with_failure() -> None:
    """flush 抛异常 → 单条失败容错。"""
    session = MagicMock()
    call_count = [0]

    async def flush_side_effect():
        call_count[0] += 1
        if call_count[0] == 1:
            raise RuntimeError("db error")

    session.flush = AsyncMock(side_effect=flush_side_effect)
    session.rollback = AsyncMock()
    session.commit = AsyncMock()

    svc = GoldenDatasetService(session)
    cases = [
        GoldenCaseCreate(
            case_name="bad",
            category=GoldenCategory.NORMAL,
            input_file_path="/tmp/x.txt",
            expected_json={},
            expected_status="pass",
        ),
        GoldenCaseCreate(
            case_name="good",
            category=GoldenCategory.NORMAL,
            input_file_path="/tmp/y.txt",
            expected_json={},
            expected_status="pass",
        ),
    ]
    result = await svc.batch_import(cases)
    assert result.total == 2
    assert result.success == 1
    assert result.failed == 1
    assert len(result.errors) == 1


@pytest.mark.asyncio
async def test_golden_list_cases_with_category_filter() -> None:
    """list_cases 支持 category 过滤。"""
    session = MagicMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=mock_result)

    svc = GoldenDatasetService(session)
    await svc.list_cases(category="normal")
    # 验证 SQL 语句被执行
    session.execute.assert_awaited()


@pytest.mark.asyncio
async def test_golden_get_case_not_found() -> None:
    """get_case 找不到 → NotFoundError。"""
    session = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=mock_result)

    svc = GoldenDatasetService(session)
    with pytest.raises(NotFoundError):
        await svc.get_case(uuid4())


@pytest.mark.asyncio
async def test_golden_count() -> None:
    """count 返回总数。"""
    session = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one.return_value = 42
    session.execute = AsyncMock(return_value=mock_result)

    svc = GoldenDatasetService(session)
    total = await svc.count()
    assert total == 42


# ============== EvalRunner.run ==============
@pytest.mark.asyncio
async def test_eval_runner_run_with_injected_case_runner() -> None:
    """EvalRunner.run 使用注入的 case_runner 跑评测。"""
    session = MagicMock()
    session.commit = AsyncMock()

    # 准备 list_cases 返回的 mock
    case1 = MagicMock()
    case1.id = uuid4()
    case1.case_name = "c1"
    case1.category = "normal"
    case1.input_file_path = "/tmp/c1"
    case1.expected_json = {
        "document_json": {"a": 1},
        "risks": [{"law_name": "法1", "article": "第一条"}],
        "overall_status": "pass",
    }
    case1.expected_status = "pass"
    case1.notes = None
    case1.created_at = datetime.utcnow()

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [case1]
    session.execute = AsyncMock(return_value=mock_result)
    session.flush = AsyncMock()

    # 注入 case_runner：返回与 expected 各字段对齐的实际输出
    async def case_runner(case):
        return {
            "document_json": {"a": 1},
            "legal_context": [{"law_name": "法1", "article": "第一条"}],
            "evidences": [{"law_name": "法1", "article": "第一条"}],
            "overall_status": "pass",
            "report_markdown": (
                "一、文件基本情况\n二、审查依据\n三、审核过程\n四、发现问题\n"
                "五、风险等级\n六、修改建议\n七、审查意见"
            ),
            "risks": [{"law_name": "法1", "article": "第一条"}],
        }

    runner = EvalRunner(session)
    record = await runner.run(
        prompt_version="v1.0.0",
        case_runner=case_runner,
    )

    assert record.prompt_version == "v1.0.0"
    assert record.total_cases == 1
    # expected == actual → 全部满分
    assert float(record.parse_acc) == 1.0
    assert float(record.retrieval_acc) == 1.0
    assert record.overall_pass is True
    session.commit.assert_awaited()


@pytest.mark.asyncio
async def test_eval_runner_run_empty_cases_raises() -> None:
    """评测集为空 → ValidationError。"""
    session = MagicMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=mock_result)

    runner = EvalRunner(session)
    with pytest.raises(ValidationError):
        await runner.run(prompt_version="v1.0.0")


@pytest.mark.asyncio
async def test_eval_runner_get_run_not_found() -> None:
    """get_run 找不到 → NotFoundError。"""
    session = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=mock_result)

    runner = EvalRunner(session)
    with pytest.raises(NotFoundError):
        await runner.get_run(uuid4())
