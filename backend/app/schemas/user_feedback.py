"""用户反馈中心 Pydantic Schema（UI-M11）。

与 app/models/user_feedback.py 字段一一对应。
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

TargetKind = Literal["report", "review", "risk", "assistant"]
Vote = Literal["up", "down", "neutral"]
Status = Literal["open", "triaged", "resolved", "wontfix"]


class UserFeedbackCreate(BaseModel):
    """提交反馈请求。"""

    target_kind: TargetKind
    target_id: str = Field(min_length=1, max_length=64)
    target_label: str = Field(min_length=1, max_length=256)
    vote: Vote
    comment: str | None = Field(default=None, max_length=2000)
    context: dict = Field(default_factory=dict)


class UserFeedbackRead(BaseModel):
    """单条反馈响应体。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    target_kind: str
    target_id: str
    target_label: str
    vote: str
    comment: str | None = None
    status: str
    admin_reply: str | None = None
    context: dict = Field(default_factory=dict)
    closed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class UserFeedbackListResponse(BaseModel):
    """反馈列表分页响应。"""

    items: list[UserFeedbackRead]
    total: int
    page: int
    page_size: int


class UserFeedbackUpdate(BaseModel):
    """用户更新：仅允许关闭（closed_at）；状态流转仅管理员可改。"""

    closed: bool | None = None


class UserFeedbackSummary(BaseModel):
    """反馈概览：按 status 聚合的计数。"""

    total: int
    by_status: dict[str, int]
