"""人工反馈服务测试 - Sprint 5 / FR-032。

覆盖：
- record 成功 + ValidationError（ai_output == human_modified）
- list_by_task
- list_unincorporated
- batch_review（高频 modify_reason 统计）
- mark_incorporated + NotFoundError
- to_read 转换
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.errors import NotFoundError, ValidationError
from app.schemas.eval import FeedbackBatchReviewResponse, FeedbackCreate
from app.services.feedback import FeedbackCaseService


def _make_case(**overrides) -> MagicMock:
    """构造 mock FeedbackCase。"""
    defaults = {
        "id": uuid4(),
        "task_id": uuid4(),
        "reviewer_id": uuid4(),
        "agent_name": "content_review",
        "section": "四、发现问题",
        "ai_output": {"risk": "low"},
        "human_modified": {"risk": "high"},
        "modify_reason": "风险等级判断错误",
        "reason_category": "risk_misjudged",
        "incorporated": False,
        "prompt_version_after": None,
        "created_at": datetime.utcnow(),
    }
    defaults.update(overrides)
    m = MagicMock()
    for k, v in defaults.items():
        setattr(m, k, v)
    return m


# ============== record ==============
@pytest.mark.asyncio
async def test_record_success() -> None:
    """正常记录反馈。"""
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()

    svc = FeedbackCaseService(session)
    feedback = FeedbackCreate(
        agent_name="content_review",
        section="四、发现问题",
        ai_output={"risk": "low"},
        human_modified={"risk": "high"},
        modify_reason="风险等级判断错误",
        reason_category="risk_misjudged",
    )
    case = await svc.record(
        task_id=uuid4(), reviewer_id=uuid4(), feedback=feedback,
    )
    session.add.assert_called_once()
    session.commit.assert_awaited_once()
    assert case.agent_name == "content_review"


@pytest.mark.asyncio
async def test_record_same_output_raises() -> None:
    """ai_output == human_modified → ValidationError。"""
    session = MagicMock()
    svc = FeedbackCaseService(session)
    feedback = FeedbackCreate(
        agent_name="x",
        ai_output={"a": 1},
        human_modified={"a": 1},
        modify_reason="无变化",
    )
    with pytest.raises(ValidationError):
        await svc.record(
            task_id=uuid4(), reviewer_id=uuid4(), feedback=feedback,
        )
    session.add.assert_not_called()


# ============== list_by_task ==============
@pytest.mark.asyncio
async def test_list_by_task() -> None:
    session = MagicMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [_make_case()]
    session.execute = AsyncMock(return_value=mock_result)

    svc = FeedbackCaseService(session)
    cases = await svc.list_by_task(uuid4())
    assert len(cases) == 1


# ============== list_unincorporated ==============
@pytest.mark.asyncio
async def test_list_unincorporated() -> None:
    session = MagicMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [
        _make_case(incorporated=False),
        _make_case(incorporated=False),
    ]
    session.execute = AsyncMock(return_value=mock_result)

    svc = FeedbackCaseService(session)
    cases = await svc.list_unincorporated()
    assert len(cases) == 2
    assert all(not c.incorporated for c in cases)


# ============== batch_review ==============
@pytest.mark.asyncio
async def test_batch_review_statistics() -> None:
    """batch_review 按 category 分组 + top reasons。"""
    cases = [
        _make_case(
            modify_reason="风险判断错误", reason_category="risk_misjudged",
        ),
        _make_case(
            modify_reason="风险判断错误", reason_category="risk_misjudged",
        ),
        _make_case(
            modify_reason="引用错误", reason_category="citation_wrong",
        ),
    ]
    session = MagicMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = cases
    session.execute = AsyncMock(return_value=mock_result)

    svc = FeedbackCaseService(session)
    result = await svc.batch_review()
    assert isinstance(result, FeedbackBatchReviewResponse)
    assert result.total_cases == 3
    assert result.by_category["risk_misjudged"] == 2
    assert result.by_category["citation_wrong"] == 1
    # top reasons 按频次排序
    top = result.top_reasons[0]
    assert top["reason"] == "风险判断错误"
    assert top["count"] == 2


@pytest.mark.asyncio
async def test_batch_review_empty() -> None:
    """无未吸收反馈 → 空统计。"""
    session = MagicMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=mock_result)

    svc = FeedbackCaseService(session)
    result = await svc.batch_review()
    assert result.total_cases == 0
    assert result.by_category == {}
    assert result.top_reasons == []


# ============== mark_incorporated ==============
@pytest.mark.asyncio
async def test_mark_incorporated_success() -> None:
    session = MagicMock()
    case = _make_case(incorporated=False, prompt_version_after=None)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = case
    session.execute = AsyncMock(return_value=mock_result)
    session.commit = AsyncMock()

    svc = FeedbackCaseService(session)
    updated = await svc.mark_incorporated(case.id, "v1.1.0")
    assert updated.incorporated is True
    assert updated.prompt_version_after == "v1.1.0"
    session.commit.assert_awaited()


@pytest.mark.asyncio
async def test_mark_incorporated_not_found() -> None:
    session = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=mock_result)

    svc = FeedbackCaseService(session)
    with pytest.raises(NotFoundError):
        await svc.mark_incorporated(uuid4(), "v1.1.0")


# ============== to_read ==============
def test_to_read_conversion() -> None:
    case = _make_case()
    read = FeedbackCaseService.to_read(case)
    assert read.id == case.id
    assert read.task_id == case.task_id
    assert read.agent_name == case.agent_name
    assert read.ai_output == case.ai_output
    assert read.human_modified == case.human_modified
    assert read.modify_reason == case.modify_reason
    assert read.incorporated == case.incorporated
    assert read.prompt_version_after == case.prompt_version_after
