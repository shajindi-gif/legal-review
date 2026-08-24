"""人工反馈 API - Sprint 5 / FR-032 人工闭环。

提供反馈记录、按任务查询、未吸收列表、Batch 复盘、标记吸收能力。
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_actor, get_audit_service, get_db
from app.core.constants import AuditAction
from app.schemas.eval import (
    FeedbackBatchReviewResponse,
    FeedbackCreate,
    FeedbackRead,
)
from app.services.audit import AuditService
from app.services.feedback import FeedbackCaseService

router = APIRouter(prefix="/feedback", tags=["feedback"])


def get_feedback_service(
    session: AsyncSession = Depends(get_db),
) -> FeedbackCaseService:
    return FeedbackCaseService(session)


# ============== 提交反馈 ==============
@router.post(
    "/tasks/{task_id}",
    response_model=FeedbackRead,
    status_code=status.HTTP_201_CREATED,
)
async def submit_feedback(
    task_id: UUID,
    req: FeedbackCreate,
    service: FeedbackCaseService = Depends(get_feedback_service),
    audit: AuditService = Depends(get_audit_service),
    actor: dict = Depends(get_actor),
) -> FeedbackRead:
    """提交人工反馈（FR-032 人工闭环）。

    请求头需携带 X-User-Id 作为 reviewer_id。
    """
    reviewer_id_str = actor.get("user_id")
    if not reviewer_id_str:
        from app.core.errors import ValidationError

        raise ValidationError("缺少 reviewer_id（X-User-Id 请求头）")

    try:
        reviewer_id = UUID(reviewer_id_str)
    except ValueError as e:
        from app.core.errors import ValidationError

        raise ValidationError(f"reviewer_id 格式非法: {reviewer_id_str}") from e

    case = await service.record(
        task_id=task_id,
        reviewer_id=reviewer_id,
        feedback=req,
    )
    await audit.log(
        action=AuditAction.REVIEW,
        actor_id=reviewer_id,
        actor_role=actor.get("role"),
        target_type="feedback_case",
        target_id=case.id,
        after_value={
            "agent_name": case.agent_name,
            "reason_category": case.reason_category,
        },
        ip_address=actor.get("ip"),
    )
    return FeedbackCaseService.to_read(case)


# ============== 查询 ==============
@router.get("/tasks/{task_id}", response_model=list[FeedbackRead])
async def list_task_feedback(
    task_id: UUID,
    service: FeedbackCaseService = Depends(get_feedback_service),
) -> list[FeedbackRead]:
    """查询任务的全部反馈。"""
    cases = await service.list_by_task(task_id)
    return [FeedbackCaseService.to_read(c) for c in cases]


@router.get("/unincorporated", response_model=list[FeedbackRead])
async def list_unincorporated(
    limit: int = Query(default=50, ge=1, le=500),
    service: FeedbackCaseService = Depends(get_feedback_service),
) -> list[FeedbackRead]:
    """查询未吸收的反馈列表（待 Prompt 优化）。"""
    cases = await service.list_unincorporated()
    return [FeedbackCaseService.to_read(c) for c in cases[:limit]]


@router.get("/batch-review", response_model=FeedbackBatchReviewResponse)
async def batch_review(
    service: FeedbackCaseService = Depends(get_feedback_service),
) -> FeedbackBatchReviewResponse:
    """周期 Batch 复盘：高频 modify_reason 统计。"""
    return await service.batch_review()


# ============== 标记吸收 ==============
@router.post(
    "/cases/{case_id}/incorporate",
    response_model=FeedbackRead,
    status_code=status.HTTP_200_OK,
)
async def mark_incorporated(
    case_id: UUID,
    prompt_version_after: str = Query(..., min_length=1, max_length=32),
    service: FeedbackCaseService = Depends(get_feedback_service),
    audit: AuditService = Depends(get_audit_service),
    actor: dict = Depends(get_actor),
) -> FeedbackRead:
    """标记反馈已被 Prompt 优化吸收。"""
    case = await service.mark_incorporated(case_id, prompt_version_after)
    await audit.log(
        action=AuditAction.MODIFY,
        actor_id=actor.get("user_id"),
        actor_role=actor.get("role"),
        target_type="feedback_case",
        target_id=case.id,
        after_value={
            "incorporated": True,
            "prompt_version_after": prompt_version_after,
        },
        ip_address=actor.get("ip"),
    )
    return FeedbackCaseService.to_read(case)
