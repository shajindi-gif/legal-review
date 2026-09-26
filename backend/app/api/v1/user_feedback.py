"""用户反馈中心 API（UI-M11）。

端点：
- POST   /user-feedback             提交反馈（FeedbackBar / 报告 / 审查调用）
- GET    /user-feedback             当前用户分页查询
- GET    /user-feedback/{id}        单条详情
- PATCH  /user-feedback/{id}        用户关闭/已读

admin 端：见 app/api/v1/admin_user_feedback.py（M11.6）。

鉴权：所有端点通过 Authorization: Bearer JWT 校验当前用户（本地 JWT 优先，Core 回退），
不再信任前端自报的 X-User-Id 头，避免越权读他人反馈。
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.errors import ValidationError
from app.schemas.user_feedback import (
    UserFeedbackCreate,
    UserFeedbackListResponse,
    UserFeedbackRead,
    UserFeedbackSummary,
    UserFeedbackUpdate,
)
from app.services.core_auth_client import CorePrincipal
from app.services.user_feedback import UserFeedbackService

router = APIRouter(prefix="/user-feedback", tags=["user-feedback"])


def get_user_feedback_service(
    session: AsyncSession = Depends(get_db),
) -> UserFeedbackService:
    return UserFeedbackService(session)


@router.post(
    "",
    response_model=UserFeedbackRead,
    status_code=status.HTTP_201_CREATED,
)
async def submit_feedback(
    req: UserFeedbackCreate,
    current_user: CorePrincipal = Depends(get_current_user),
    service: UserFeedbackService = Depends(get_user_feedback_service),
) -> UserFeedbackRead:
    """提交一条用户反馈。"""
    record = await service.create(user_id=current_user.id, payload=req)
    return UserFeedbackRead.model_validate(record)


@router.get("/summary", response_model=UserFeedbackSummary)
async def my_feedback_summary(
    current_user: CorePrincipal = Depends(get_current_user),
    service: UserFeedbackService = Depends(get_user_feedback_service),
) -> UserFeedbackSummary:
    """当前用户的反馈概览（按 status 计数）。"""
    data = await service.summary_for_user(user_id=current_user.id)
    return UserFeedbackSummary(**data)


@router.get("", response_model=UserFeedbackListResponse)
async def list_my_feedback(
    status_filter: str | None = Query(default=None, alias="status"),
    target_kind: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: CorePrincipal = Depends(get_current_user),
    service: UserFeedbackService = Depends(get_user_feedback_service),
) -> UserFeedbackListResponse:
    """查询当前用户提交的反馈（按 status / target_kind 筛选）。"""
    items, total = await service.list_for_user(
        user_id=current_user.id,
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


@router.get("/{feedback_id}", response_model=UserFeedbackRead)
async def get_my_feedback(
    feedback_id: UUID,
    current_user: CorePrincipal = Depends(get_current_user),
    service: UserFeedbackService = Depends(get_user_feedback_service),
) -> UserFeedbackRead:
    """单条详情（仅本人可看）。"""
    record = await service.get_for_user(user_id=current_user.id, feedback_id=feedback_id)
    return UserFeedbackRead.model_validate(record)


@router.patch("/{feedback_id}", response_model=UserFeedbackRead)
async def close_my_feedback(
    feedback_id: UUID,
    req: UserFeedbackUpdate,
    current_user: CorePrincipal = Depends(get_current_user),
    service: UserFeedbackService = Depends(get_user_feedback_service),
) -> UserFeedbackRead:
    """用户主动关闭（已读）。

    status / admin_reply 用户无权修改；仅 closed 字段由用户控制。
    """
    if req.closed is False:
        # 用户想"重新打开"——暂不支持（M11 范围外）
        raise ValidationError("不支持重新打开反馈，请联系管理员")
    if req.closed is True:
        record = await service.mark_closed(user_id=current_user.id, feedback_id=feedback_id)
    else:
        # req.closed is None：no-op
        record = await service.get_for_user(user_id=current_user.id, feedback_id=feedback_id)
    return UserFeedbackRead.model_validate(record)