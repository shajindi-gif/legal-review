"""评测系统 Pydantic Schemas - Sprint 5 / FR-029/031/032/035。"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.constants import GoldenCategory


# ============== Golden Dataset ==============
class GoldenCaseCreate(BaseModel):
    """导入 Golden Case 请求。"""

    case_name: str = Field(..., min_length=1, max_length=255)
    category: GoldenCategory
    input_file_path: str = Field(..., min_length=1, max_length=512)
    expected_json: dict[str, Any]
    expected_status: str = Field(..., max_length=16)
    notes: str | None = None


class GoldenCaseRead(BaseModel):
    """Golden Case 查询响应。"""

    id: UUID
    case_name: str
    category: str
    input_file_path: str
    expected_json: dict[str, Any]
    expected_status: str
    notes: str | None = None
    created_at: datetime


class GoldenBatchImportRequest(BaseModel):
    """批量导入请求（POST body）。"""

    cases: list[GoldenCaseCreate]


class GoldenBatchImportResponse(BaseModel):
    """批量导入响应。"""

    total: int
    success: int
    failed: int
    errors: list[str] = Field(default_factory=list)


# ============== EvalRun ==============
class EvalRunCreate(BaseModel):
    """触发评测请求。"""

    prompt_version: str = Field(..., min_length=1)
    categories: list[GoldenCategory] | None = None
    max_cases: int | None = Field(default=None, ge=1, le=500)


class EvalRunRead(BaseModel):
    """评测运行查询响应。"""

    id: UUID
    run_id: UUID
    prompt_version: str
    started_at: datetime
    finished_at: datetime | None
    total_cases: int
    parse_acc: float | None
    retrieval_acc: float | None
    citation_acc: float | None
    risk_kappa: float | None
    report_complete: float | None
    hallucination_rate: float | None
    overall_pass: bool | None
    raw_result_path: str | None


# ============== Feedback ==============
class FeedbackCreate(BaseModel):
    """提交人工反馈请求（FR-032）。"""

    agent_name: str = Field(..., min_length=1, max_length=64)
    section: str | None = Field(default=None, max_length=64)
    ai_output: dict[str, Any]
    human_modified: dict[str, Any]
    modify_reason: str = Field(..., min_length=1)
    reason_category: str | None = Field(default=None, max_length=32)


class FeedbackRead(BaseModel):
    """反馈查询响应。"""

    id: UUID
    task_id: UUID
    reviewer_id: UUID
    agent_name: str
    section: str | None
    ai_output: dict[str, Any]
    human_modified: dict[str, Any]
    modify_reason: str
    reason_category: str | None
    incorporated: bool
    prompt_version_after: str | None
    created_at: datetime


class FeedbackBatchReviewResponse(BaseModel):
    """周期 Batch 复盘响应。"""

    total_cases: int
    by_category: dict[str, int]
    top_reasons: list[dict[str, Any]]
