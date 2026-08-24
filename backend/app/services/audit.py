"""审计日志服务 - 全链路操作入审计表（合规要求保留 3 年）。"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import AuditAction
from app.models.platform import AuditRecord


class AuditService:
    """审计日志写入。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def log(
        self,
        *,
        action: AuditAction | str,
        actor_id: UUID | None = None,
        actor_role: str | None = None,
        target_type: str | None = None,
        target_id: UUID | None = None,
        trace_id: UUID | None = None,
        before_value: dict[str, Any] | None = None,
        after_value: dict[str, Any] | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AuditRecord:
        """写入一条审计记录。"""
        record = AuditRecord(
            trace_id=trace_id or uuid4(),
            actor_id=actor_id,
            actor_role=actor_role,
            action=str(action),
            target_type=target_type,
            target_id=target_id,
            before_value=before_value,
            after_value=after_value,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self._session.add(record)
        await self._session.flush()
        return record
