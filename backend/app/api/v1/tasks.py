"""任务查询 API - FR-033（任务看板）+ FR-008（解析结果预览）。

鉴权（Sprint 6.4）：
- 必须携带 Authorization: Bearer <access_token>
- submitter/reviewer 只能看自己的任务
- supervisor/admin 可看所有任务
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.errors import AppError, NotFoundError
from app.models.document import Document
from app.models.task import ReviewResult, ReviewTask
from app.models.user import User
from app.schemas.document import DocumentRead
from app.schemas.task import TaskRead, TaskStatusResponse, TaskListResponse

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _can_view_all(user: User) -> bool:
    """判断用户是否有权查看全部任务。"""
    return str(user.role) in {"supervisor", "admin"}


async def _load_task(
    db: AsyncSession, task_id: UUID, *, current_user: User
) -> ReviewTask:
    """查询任务并校验访问权限。

    - admin/supervisor：可看所有任务
    - submitter/reviewer/librarian：仅可看自己的任务
    """
    result = await db.execute(
        select(ReviewTask).where(
            ReviewTask.id == task_id, ReviewTask.deleted_at.is_(None)
        )
    )
    task = result.scalar_one_or_none()
    if task is None:
        raise NotFoundError("ReviewTask", str(task_id))
    if not _can_view_all(current_user) and task.submitter_id != current_user.id:
        raise NotFoundError("ReviewTask", str(task_id))
    return task


@router.get("", response_model=TaskListResponse)
async def list_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None, description="按状态过滤"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TaskListResponse:
    """查询任务列表（FR-033 看板）。

    - submitter/reviewer/librarian：仅返回自己的任务
    - supervisor/admin：返回全部
    """
    base = select(ReviewTask).where(ReviewTask.deleted_at.is_(None))
    count_base = select(func.count(ReviewTask.id)).where(
        ReviewTask.deleted_at.is_(None)
    )
    if not _can_view_all(current_user):
        base = base.where(ReviewTask.submitter_id == current_user.id)
        count_base = count_base.where(ReviewTask.submitter_id == current_user.id)
    if status:
        base = base.where(ReviewTask.status == status)
        count_base = count_base.where(ReviewTask.status == status)

    total = (await db.execute(count_base)).scalar_one()
    base = base.order_by(desc(ReviewTask.submitted_at))
    base = base.offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(base)).scalars().all()
    return TaskListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[TaskRead.model_validate(r, from_attributes=True) for r in rows],
    )


@router.get("/{task_id}", response_model=TaskRead)
async def get_task(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TaskRead:
    """查询任务详情。"""
    task = await _load_task(db, task_id, current_user=current_user)
    return TaskRead.model_validate(task, from_attributes=True)


@router.get("/{task_id}/status", response_model=TaskStatusResponse)
async def get_task_status(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TaskStatusResponse:
    """查询任务状态与进度。"""
    task = await _load_task(db, task_id, current_user=current_user)
    progress_map = {
        "doc_parse": 0.1,
        "doc_classify": 0.2,
        "legal_retrieve": 0.3,
        "authority_review": 0.4,
        "procedure_review": 0.5,
        "content_review": 0.6,
        "risk_assessment": 0.7,
        "evidence_verify": 0.8,
        "report_generation": 0.9,
        "human_review": 0.95,
    }
    progress = progress_map.get(task.current_node or "", 0.0)
    if task.status == "done":
        progress = 1.0

    return TaskStatusResponse(
        task_id=task.id,
        trace_id=task.trace_id,
        status=task.status,
        current_node=task.current_node,
        progress=progress,
        iteration=task.iteration,
        max_iteration=task.max_iteration,
    )


@router.get("/{task_id}/documents", response_model=list[DocumentRead])
async def list_documents(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[DocumentRead]:
    """查询任务下的全部文件。"""
    task = await _load_task(db, task_id, current_user=current_user)
    result = await db.execute(
        select(Document).where(
            Document.task_id == task.id, Document.deleted_at.is_(None)
        )
    )
    docs = result.scalars().all()
    return [DocumentRead.model_validate(d, from_attributes=True) for d in docs]


@router.get("/{task_id}/documents/{document_id}", response_model=DocumentRead)
async def get_document(
    task_id: UUID,
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DocumentRead:
    """查询单个文件（含 parsed_json 解析结果）。"""
    task = await _load_task(db, task_id, current_user=current_user)
    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.task_id == task.id,
            Document.deleted_at.is_(None),
        )
    )
    doc = result.scalar_one_or_none()
    if doc is None:
        raise AppError(
            http_status=404,
            code="DOCUMENT_NOT_FOUND",
            message=f"文件 {document_id} 不存在或已删除",
        )
    return DocumentRead.model_validate(doc, from_attributes=True)


@router.get("/{task_id}/report", response_model=dict)
async def get_task_report(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """拉取任务的最终报告。

    来源：report_generation 节点的 ReviewResult.output_json.report_markdown。
    若任务尚未到 report_generation 节点，返回 404 + 明确错误。
    """
    task = await _load_task(db, task_id, current_user=current_user)
    result = await db.execute(
        select(ReviewResult)
        .where(
            ReviewResult.task_id == task.id,
            ReviewResult.agent_name == "report_generation",
        )
        .order_by(desc(ReviewResult.created_at))
        .limit(1)
    )
    rr = result.scalar_one_or_none()
    if rr is None:
        raise AppError(
            http_status=404,
            code="REPORT_NOT_READY",
            message=f"任务 {task_id} 尚未生成报告（当前节点：{task.current_node}）",
        )
    md = (rr.output_json or {}).get("report_markdown") or ""
    return {
        "task_id": str(task.id),
        "status": str(task.status),
        "report_markdown": md,
        "risks": rr.risks or [],
        "evidences": rr.evidences or [],
    }
