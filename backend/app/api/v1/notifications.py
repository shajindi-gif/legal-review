"""通知中心 API - UI-M8。

端点：
- GET    /api/v1/notifications              分页列表（带 unread_count）
- GET    /api/v1/notifications/unread-count 仅返回 unread_count（30s 轮询）
- POST   /api/v1/notifications/{id}/read   标记单条已读
- POST   /api/v1/notifications/read-all    全部已读

鉴权：get_current_user（M8 仅本人 inbox；admin 全量先不做）。
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.notification import (
    NotificationListResponse,
    NotificationRead,
    NotificationUnreadCount,
)
from app.services.notification import NotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])


def get_service(session: AsyncSession = Depends(get_db)) -> NotificationService:
    return NotificationService(session)


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    only_unread: bool = Query(False, description="只看未读"),
    service: NotificationService = Depends(get_service),
    current_user: User = Depends(get_current_user),
) -> NotificationListResponse:
    """通知列表（分页）。"""
    items, total, unread = await service.list_for_user(
        current_user.id, page=page, page_size=page_size, only_unread=only_unread
    )
    return NotificationListResponse(
        items=[NotificationRead.model_validate(i) for i in items],
        total=total,
        unread_count=unread,
        page=page,
        page_size=page_size,
    )


@router.get("/unread-count", response_model=NotificationUnreadCount)
async def unread_count(
    service: NotificationService = Depends(get_service),
    current_user: User = Depends(get_current_user),
) -> NotificationUnreadCount:
    """仅返回未读数（铃铛 badge 30s 轮询）。"""
    n = await service.unread_count(current_user.id)
    return NotificationUnreadCount(unread_count=n)


@router.post(
    "/{notif_id}/read",
    response_model=NotificationRead,
    status_code=status.HTTP_200_OK,
)
async def mark_read(
    notif_id: UUID,
    service: NotificationService = Depends(get_service),
    current_user: User = Depends(get_current_user),
) -> NotificationRead:
    """标记单条已读。"""
    notif = await service.mark_read(current_user.id, notif_id)
    return NotificationRead.model_validate(notif)


@router.post("/read-all", response_model=NotificationUnreadCount)
async def mark_all_read(
    service: NotificationService = Depends(get_service),
    current_user: User = Depends(get_current_user),
) -> NotificationUnreadCount:
    """全部已读，返回剩余未读数（应为 0）。"""
    affected = await service.mark_all_read(current_user.id)
    # 全部已读后未读数应=0，但仍按 DB 真实值回（避免历史脏数据）
    _ = affected
    n = await service.unread_count(current_user.id)
    return NotificationUnreadCount(unread_count=n)
