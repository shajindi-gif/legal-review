"""通知中心 Pydantic Schema（UI-M8）。

与 app/models/notification.py 字段一一对应。
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class NotificationRead(BaseModel):
    """单条通知响应体。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kind: str
    title: str
    body: str | None = None
    task_id: UUID | None = None
    link: str | None = None
    payload: dict = Field(default_factory=dict)
    read_at: datetime | None = None
    created_at: datetime


class NotificationListResponse(BaseModel):
    """通知列表（分页 + 未读数）。"""

    items: list[NotificationRead]
    total: int
    unread_count: int
    page: int
    page_size: int


class NotificationUnreadCount(BaseModel):
    """仅返回未读数（铃铛 badge 用，30s 轮询）。"""

    unread_count: int
