"""任务相关 Pydantic Schema。"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TaskCreate(BaseModel):
    """创建任务请求。"""
    title: str = Field(..., min_length=1, max_length=255)
    submitter_org_id: UUID
    priority: str = Field("normal", description="low|normal|high|urgent")


class TaskRead(BaseModel):
    """任务查询响应。

    注：ORM 字段名是 metadata_（避开 SQLAlchemy 保留属性 metadata），
    用 alias 让 from_attributes 从 metadata_ 读取。
    """
    model_config = ConfigDict(populate_by_name=True)

    id: UUID
    trace_id: UUID
    title: str
    status: str
    current_node: str | None
    iteration: int
    max_iteration: int
    priority: str
    submitted_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    due_at: datetime | None
    metadata: dict[str, Any] = Field(default_factory=dict, alias="metadata_")
    created_at: datetime


class TaskStatusResponse(BaseModel):
    """任务状态查询响应（含进度）。"""
    task_id: UUID
    trace_id: UUID
    status: str
    current_node: str | None
    progress: float = Field(ge=0.0, le=1.0, description="0.0-1.0")
    iteration: int
    max_iteration: int
    estimated_remaining_sec: int | None = None


class TaskListResponse(BaseModel):
    """任务列表分页响应。"""
    total: int
    page: int
    page_size: int
    items: list["TaskRead"]


class ReviewTriggerRequest(BaseModel):
    """审查触发请求。"""
    force_recheck: bool = False


class FeedbackRequest(BaseModel):
    """人工反馈回流请求。"""
    section: str
    original: dict[str, Any]
    modified: dict[str, Any]
    reason: str = Field(..., min_length=1)
    reason_category: str | None = None
