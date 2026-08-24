"""人工反馈服务 - Sprint 5 / FR-031/032 人工闭环。

职责：
1. record(): 记录人工修改（ai_output vs human_modified + modify_reason）
2. list_by_task(): 查询任务反馈历史
3. batch_review(): 周期 Batch 复盘（统计高频 modify_reason）
4. mark_incorporated(): 标记反馈已被 Prompt 优化吸收

硬约束：
- 人工闭环不可省（硬约束#8）
- 反馈写入 feedback_cases 表（长期保留作为案例库资产）
"""

from __future__ import annotations

from collections import Counter
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.platform import FeedbackCase
from app.schemas.eval import (
    FeedbackBatchReviewResponse,
    FeedbackCreate,
    FeedbackRead,
)

logger = get_logger("services.feedback")


class FeedbackCaseService:
    """人工反馈案例管理。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        *,
        task_id: UUID,
        reviewer_id: UUID,
        feedback: FeedbackCreate,
    ) -> FeedbackCase:
        """记录一条人工反馈。

        Args:
            task_id: 关联的审查任务 ID
            reviewer_id: 审查员 ID
            feedback: 反馈内容（agent_name + ai_output + human_modified + reason）
        """
        if feedback.ai_output == feedback.human_modified:
            raise ValidationError(
                "ai_output 与 human_modified 相同，无需记录反馈"
            )
        record = FeedbackCase(
            task_id=task_id,
            reviewer_id=reviewer_id,
            agent_name=feedback.agent_name,
            section=feedback.section,
            ai_output=feedback.ai_output,
            human_modified=feedback.human_modified,
            modify_reason=feedback.modify_reason,
            reason_category=feedback.reason_category,
            incorporated=False,
        )
        self._session.add(record)
        await self._session.commit()
        logger.info(
            "feedback_recorded",
            task_id=str(task_id), agent=feedback.agent_name,
            reason_category=feedback.reason_category,
        )
        return record

    async def list_by_task(self, task_id: UUID) -> list[FeedbackCase]:
        """查询任务的全部反馈。"""
        stmt = (
            select(FeedbackCase)
            .where(FeedbackCase.task_id == task_id)
            .order_by(FeedbackCase.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_unincorporated(self) -> list[FeedbackCase]:
        """查询未吸收的反馈（incorporated=false）。"""
        stmt = (
            select(FeedbackCase)
            .where(FeedbackCase.incorporated.is_(False))
            .order_by(FeedbackCase.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def batch_review(self) -> FeedbackBatchReviewResponse:
        """周期 Batch 复盘：统计高频 modify_reason。

        输出按 reason_category 分组 + top reasons 排序。
        """
        cases = await self.list_unincorporated()
        category_counter: Counter[str] = Counter()
        reason_counter: Counter[str] = Counter()
        for case in cases:
            cat = case.reason_category or "uncategorized"
            category_counter[cat] += 1
            reason_counter[case.modify_reason] += 1

        top_reasons = [
            {"reason": r, "count": c}
            for r, c in reason_counter.most_common(10)
        ]
        return FeedbackBatchReviewResponse(
            total_cases=len(cases),
            by_category=dict(category_counter),
            top_reasons=top_reasons,
        )

    async def mark_incorporated(
        self, case_id: UUID, prompt_version_after: str,
    ) -> FeedbackCase:
        """标记反馈已被 Prompt 优化吸收。"""
        stmt = select(FeedbackCase).where(FeedbackCase.id == case_id)
        result = await self._session.execute(stmt)
        record = result.scalar_one_or_none()
        if record is None:
            raise NotFoundError("FeedbackCase", str(case_id))
        record.incorporated = True  # type: ignore[misc]
        record.prompt_version_after = prompt_version_after  # type: ignore[assignment]
        await self._session.commit()
        logger.info(
            "feedback_incorporated",
            case_id=str(case_id),
            prompt_version_after=prompt_version_after,
        )
        return record

    @staticmethod
    def to_read(case: FeedbackCase) -> FeedbackRead:
        """ORM → Pydantic Read。"""
        return FeedbackRead(
            id=case.id,
            task_id=case.task_id,
            reviewer_id=case.reviewer_id,
            agent_name=case.agent_name,
            section=case.section,
            ai_output=case.ai_output,
            human_modified=case.human_modified,
            modify_reason=case.modify_reason,
            reason_category=case.reason_category,
            incorporated=case.incorporated,
            prompt_version_after=case.prompt_version_after,
            created_at=case.created_at,
        )
