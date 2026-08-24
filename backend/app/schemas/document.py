"""文件相关 Pydantic Schema。"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class DocumentUploadResponse(BaseModel):
    """文件上传响应（FR-001 ~ FR-010）。"""
    task_id: UUID
    trace_id: UUID
    document_id: UUID
    original_name: str
    file_type: str
    file_size: int
    file_hash: str = Field(..., description="sha256")
    storage_path: str = Field(..., description="沙箱内相对路径，不暴露绝对路径")
    parse_status: str = "pending"
    status: str = "parsing"


class DocumentRead(BaseModel):
    """文件查询响应。"""
    id: UUID
    task_id: UUID
    original_name: str
    file_type: str
    file_size: int
    file_hash: str
    parse_status: str
    parsed_json: dict[str, Any] | None = None
    created_at: datetime


class ParagraphItem(BaseModel):
    """正文段落（含 anchor 用于回链）。"""
    id: str = Field(description="段落 ID，如 p1")
    text: str
    anchor: str = Field(description="HTML/PDF 锚点，如 #p1")


class AttachmentItem(BaseModel):
    """附件。"""
    name: str
    path: str
    size: int | None = None


class DocumentJson(BaseModel):
    """文件结构化输出 Schema（来自 Agent Graph 3.1）。

    用于 doc_parse 节点产出，存入 documents.parsed_json。
    """
    title: str | None = None
    issuing_authority: str | None = None
    publish_date: str | None = None
    effective_date: str | None = None
    doc_number: str | None = None
    body_paragraphs: list[ParagraphItem] = Field(default_factory=list)
    attachments: list[AttachmentItem] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    policy_domain: str | None = None
    parser_version: str = "v1.0.0"
