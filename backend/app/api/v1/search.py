"""全局搜索 API - UI-M12 ⌘K。

设计原则：
- 单端点聚合多源（tasks / documents / reports），前端不需要并发请求 3 个 list
- 复用 tasks.py 的鉴权规则：supervisor/admin 看全部，其它角色仅自己的资源
- 算法：ILIKE %q%（MVP 阶段够用；后续可换 PG full-text / pg_trgm）
- q 长度上限 64 字符，避免 ILIKE 通配符爆炸
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.document import Document
from app.models.task import ReviewResult, ReviewTask
from app.models.user import User
from app.schemas.search import (
    SearchDocumentHit,
    SearchReportHit,
    SearchResponse,
    SearchTaskHit,
)

router = APIRouter(prefix="/search", tags=["search"])

MAX_QUERY_LEN = 64
DEFAULT_HIT_LIMIT = 10


def _can_view_all(user: User) -> bool:
    return str(user.role) in {"supervisor", "admin"}


def _build_like(q: str) -> str:
    """统一 ILIKE 模式：%q%。"""
    return f"%{q}%"


@router.get("", response_model=SearchResponse)
async def global_search(
    q: str = Query("", description="查询词（trim 后，长度 1-64）"),
    limit: int = Query(DEFAULT_HIT_LIMIT, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SearchResponse:
    """⌘K 全局搜索。

    返回三组命中：
    - tasks: ReviewTask.title 匹配
    - documents: Document.original_name 匹配（同时带出 task_id）
    - reports: 已生成报告的 task（按 task.title 匹配；过滤 done 状态）
    """
    q = (q or "").strip()
    if not q:
        return SearchResponse(q="")
    if len(q) > MAX_QUERY_LEN:
        q = q[:MAX_QUERY_LEN]

    can_view_all = _can_view_all(current_user)
    like = _build_like(q)

    task_stmt = (
        select(ReviewTask)
        .where(ReviewTask.deleted_at.is_(None))
        .where(ReviewTask.title.ilike(like))
        .order_by(desc(ReviewTask.submitted_at))
        .limit(limit)
    )
    if not can_view_all:
        task_stmt = task_stmt.where(ReviewTask.submitter_id == current_user.id)

    task_rows = (await db.execute(task_stmt)).scalars().all()
    tasks = [
        SearchTaskHit(
            id=t.id,
            title=t.title,
            status=str(t.status),
            priority=str(t.priority),
            submitted_at=t.submitted_at,
            completed_at=t.completed_at,
        )
        for t in task_rows
    ]

    doc_stmt = (
        select(Document)
        .where(Document.deleted_at.is_(None))
        .where(Document.original_name.ilike(like))
        .order_by(desc(Document.created_at))
        .limit(limit)
    )
    if not can_view_all:
        doc_stmt = doc_stmt.join(
            ReviewTask, Document.task_id == ReviewTask.id
        ).where(ReviewTask.submitter_id == current_user.id)

    doc_rows = (await db.execute(doc_stmt)).scalars().all()
    documents = [
        SearchDocumentHit(
            id=d.id,
            task_id=d.task_id,
            original_name=d.original_name,
            file_type=str(d.file_type),
            file_size=d.file_size,
            parse_status=str(d.parse_status),
            created_at=d.created_at,
        )
        for d in doc_rows
    ]

    # 报告 = 已生成 review_result.report_generation 的 task（按 task.title 匹配）
    report_subq = (
        select(ReviewResult.task_id)
        .where(ReviewResult.agent_name == "report_generation")
        .distinct()
        .subquery()
    )
    report_stmt = (
        select(ReviewTask)
        .where(ReviewTask.deleted_at.is_(None))
        .where(ReviewTask.id.in_(select(report_subq.c.task_id)))
        .where(ReviewTask.title.ilike(like))
        .order_by(desc(ReviewTask.completed_at))
        .limit(limit)
    )
    if not can_view_all:
        report_stmt = report_stmt.where(
            ReviewTask.submitter_id == current_user.id
        )

    report_rows = (await db.execute(report_stmt)).scalars().all()
    reports = [
        SearchReportHit(
            task_id=t.id,
            title=t.title,
            status=str(t.status),
            completed_at=t.completed_at,
            has_report=True,
        )
        for t in report_rows
    ]

    return SearchResponse(q=q, tasks=tasks, documents=documents, reports=reports)
