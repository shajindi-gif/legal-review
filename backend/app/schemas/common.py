"""通用响应 Schema - 统一 envelope + 分页 + trace。"""

from __future__ import annotations

from typing import Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, Field

T = TypeVar("T")


class TraceEnvelope(BaseModel):
    """带 trace_id 的统一响应。"""
    trace_id: UUID
    data: dict | list | None = None
    error: dict | None = None


class PageMeta(BaseModel):
    """分页元信息。"""
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=200)
    total: int = Field(ge=0)


class Page(BaseModel, Generic[T]):
    """分页响应。"""
    items: list[T]
    meta: PageMeta
