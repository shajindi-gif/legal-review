"""Admin 端：用户反馈管理 API（UI-M11.6）。

端点：
- GET    /admin/user-feedback            全量分页查询（按 status / target_kind 筛选）
- GET    /admin/user-feedback/summary    概览统计
- PATCH  /admin/user-feedback/{id}       更新 status / admin_reply
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_actor, get_db
from app.core.errors import AuthError, ValidationError
from app.schemas.user_feedback import UserFeedbackListResponse, UserFeedbackRead
from app.services.user_feedback import UserFeedbackService

router = APIRouter(prefix="/admin/user-feedback", tags=["admin-user-feedback"])


def get_admin_feedback_service(
    session: AsyncSession = Depends(get_db),
) -> UserFeedbackService:
    return UserFeedbackService(session)


def _require_admin(actor: dict) -> None:
    role = (actor.get("role") or "").lower()
    if role not in {"admin", "supervisor"}:
        raise AuthError("仅管理员/监督员可访问反馈管理")


@router.get("", response_model=UserFeedbackListResponse)
async def admin_list_feedback(
    status_filter: str | None = Query(default=None, alias="status"),
    target_kind: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    actor: dict = Depends(get_actor),
    service: UserFeedbackService = Depends(get_admin_feedback_service),
) -> UserFeedbackListResponse:
    """管理员全量查询。"""
    _require_admin(actor)
    items, total = await service.list_for_admin(
        status=status_filter,
        target_kind=target_kind,
        page=page,
        page_size=page_size,
    )
    return UserFeedbackListResponse(
        items=[UserFeedbackRead.model_validate(i) for i in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/summary")
async def admin_feedback_summary(
    actor: dict = Depends(get_actor),
    service: UserFeedbackService = Depends(get_admin_feedback_service),
) -> dict:
    """管理员概览：按 status 计数 + 总数。"""
    _require_admin(actor)
    return await service.summary()


class AdminFeedbackUpdate(BaseModel):
    """管理员更新反馈的请求体。"""

    status: str | None = None
    admin_reply: str | None = Field(default=None, max_length=1000)


@router.patch("/{feedback_id}", response_model=UserFeedbackRead)
async def admin_update_feedback(
    feedback_id: UUID,
    req: AdminFeedbackUpdate,
    actor: dict = Depends(get_actor),
    service: UserFeedbackService = Depends(get_admin_feedback_service),
) -> UserFeedbackRead:
    """管理员更新 status / admin_reply。"""
    _require_admin(actor)
    if req.status is None and req.admin_reply is None:
        raise ValidationError("至少提供 status 或 admin_reply 之一")
    record = await service.admin_update(
        feedback_id=feedback_id,
        status=req.status,
        admin_reply=req.admin_reply,
    )
    return UserFeedbackRead.model_validate(record)
