"""全局搜索 Schema - UI-M12 ⌘K。"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class SearchTaskHit(BaseModel):
    """搜索结果：任务命中。"""

    id: UUID
    title: str
    status: str
    priority: str
    submitted_at: datetime
    completed_at: datetime | None = None


class SearchDocumentHit(BaseModel):
    """搜索结果：文件命中。"""

    id: UUID
    task_id: UUID
    original_name: str
    file_type: str
    file_size: int
    parse_status: str
    created_at: datetime


class SearchReportHit(BaseModel):
    """搜索结果：报告命中（借任务 title 表达）。"""

    task_id: UUID
    title: str
    status: str
    completed_at: datetime | None = None
    has_report: bool = True


class SearchResponse(BaseModel):
    """⌘K 全局搜索响应。"""

    q: str = Field(description="查询词（已 trim）")
    tasks: list[SearchTaskHit] = Field(default_factory=list)
    documents: list[SearchDocumentHit] = Field(default_factory=list)
    reports: list[SearchReportHit] = Field(default_factory=list)
