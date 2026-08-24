"""审计日志 API - Sprint 5 / FR-035 全链路可观测性。

提供审计日志查询能力（合规要求保留 3 年）。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.platform import AuditRecord

router = APIRouter(prefix="/audit", tags=["audit"])


class AuditRecordRead(BaseModel):
    """审计记录响应。"""

    id: UUID
    trace_id: UUID | None
    actor_id: UUID | None
    actor_role: str | None
    action: str
    target_type: str | None
    target_id: UUID | None
    before_value: dict[str, Any] | None
    after_value: dict[str, Any] | None
    ip_address: str | None
    user_agent: str | None
    created_at: datetime


def _to_read(rec: AuditRecord) -> AuditRecordRead:
    return AuditRecordRead(
        id=rec.id,
        trace_id=rec.trace_id,
        actor_id=rec.actor_id,
        actor_role=rec.actor_role,
        action=rec.action,
        target_type=rec.target_type,
        target_id=rec.target_id,
        before_value=rec.before_value,
        after_value=rec.after_value,
        ip_address=rec.ip_address,
        user_agent=rec.user_agent,
        created_at=rec.created_at,
    )


@router.get("/records", response_model=list[AuditRecordRead])
async def list_audit_records(
    trace_id: UUID | None = Query(default=None),
    action: str | None = Query(default=None),
    target_type: str | None = Query(default=None),
    actor_id: UUID | None = Query(default=None),
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    session: AsyncSession = Depends(get_db),
) -> list[AuditRecordRead]:
    """审计日志查询（支持多维度过滤）。

    可按 trace_id 追踪全链路操作，或按 actor/action/target 过滤。
    """
    stmt = select(AuditRecord).order_by(AuditRecord.created_at.desc())
    if trace_id is not None:
        stmt = stmt.where(AuditRecord.trace_id == trace_id)
    if action is not None:
        stmt = stmt.where(AuditRecord.action == action)
    if target_type is not None:
        stmt = stmt.where(AuditRecord.target_type == target_type)
    if actor_id is not None:
        stmt = stmt.where(AuditRecord.actor_id == actor_id)
    if start_time is not None:
        stmt = stmt.where(AuditRecord.created_at >= start_time)
    if end_time is not None:
        stmt = stmt.where(AuditRecord.created_at <= end_time)

    offset = (page - 1) * page_size
    stmt = stmt.offset(offset).limit(page_size)

    result = await session.execute(stmt)
    return [_to_read(r) for r in result.scalars().all()]


@router.get("/trace/{trace_id}", response_model=list[AuditRecordRead])
async def list_by_trace(
    trace_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> list[AuditRecordRead]:
    """按 trace_id 查询全链路操作（FR-035 trace 追踪）。"""
    stmt = (
        select(AuditRecord)
        .where(AuditRecord.trace_id == trace_id)
        .order_by(AuditRecord.created_at.asc())
    )
    result = await session.execute(stmt)
    return [_to_read(r) for r in result.scalars().all()]


@router.get("/records/{record_id}", response_model=AuditRecordRead)
async def get_audit_record(
    record_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> AuditRecordRead:
    """查询单条审计记录。"""
    from app.core.errors import NotFoundError

    stmt = select(AuditRecord).where(AuditRecord.id == record_id)
    result = await session.execute(stmt)
    rec = result.scalar_one_or_none()
    if rec is None:
        raise NotFoundError("AuditRecord", str(record_id))
    return _to_read(rec)


@router.get("/count")
async def count_audit_records(
    session: AsyncSession = Depends(get_db),
) -> dict:
    """统计审计日志总数。"""
    from sqlalchemy import func

    stmt = select(func.count(AuditRecord.id))
    result = await session.execute(stmt)
    return {"total": result.scalar_one()}
