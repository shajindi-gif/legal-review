"""通知 Service（UI-M8）。

提供 4 个核心方法：
- create：单个通知落库（被 agent 节点钩子调用）
- list_for_user：分页查询 + 顺手回 unread_count
- unread_count：仅取 COUNT(*) WHERE read_at IS NULL
- mark_read：标记单条为已读
- mark_all_read：全部已读

设计要点：
- create 是 sync 友好的 asyncio 函数（节点钩子可 fire-and-forget 排队 task）
- 全部按 recipient_id 隔离，越权访问会抛 NotFoundError
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.models.notification import Notification


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class NotificationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ============== 写入 ==============
    async def create(
        self,
        *,
        recipient_id: UUID,
        kind: str,
        title: str,
        body: str | None = None,
        task_id: UUID | None = None,
        link: str | None = None,
        payload: dict | None = None,
    ) -> Notification:
        """插入一条通知。供 agent 节点钩子调用。"""
        notif = Notification(
            recipient_id=recipient_id,
            kind=kind,
            title=title,
            body=body,
            task_id=task_id,
            link=link,
            payload=payload or {},
        )
        self.session.add(notif)
        await self.session.flush()
        return notif

    # ============== 读取 ==============
    async def list_for_user(
        self,
        user_id: UUID,
        *,
        page: int = 1,
        page_size: int = 20,
        only_unread: bool = False,
    ) -> tuple[list[Notification], int, int]:
        """分页 + 未读数一并返回（一次查询三件事：items / total / unread_count）。"""
        base = select(Notification).where(Notification.recipient_id == user_id)
        if only_unread:
            base = base.where(Notification.read_at.is_(None))

        total = (
            await self.session.execute(
                select(func.count(Notification.id)).where(
                    Notification.recipient_id == user_id,
                    *( [Notification.read_at.is_(None)] if only_unread else [] ),
                )
            )
        ).scalar_one()

        items_q = (
            base.order_by(desc(Notification.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = (await self.session.execute(items_q)).scalars().all()

        unread = (
            await self.session.execute(
                select(func.count(Notification.id)).where(
                    Notification.recipient_id == user_id,
                    Notification.read_at.is_(None),
                )
            )
        ).scalar_one()

        return list(items), total, unread

    async def unread_count(self, user_id: UUID) -> int:
        """仅取未读数。30s 轮询热点路径，保持轻量。"""
        n = (
            await self.session.execute(
                select(func.count(Notification.id)).where(
                    Notification.recipient_id == user_id,
                    Notification.read_at.is_(None),
                )
            )
        ).scalar_one()
        return int(n)

    # ============== 标记已读 ==============
    async def mark_read(self, user_id: UUID, notif_id: UUID) -> Notification:
        """标记单条已读，越权 → NotFoundError（与 tasks API 一致）。"""
        result = await self.session.execute(
            select(Notification).where(
                Notification.id == notif_id,
                Notification.recipient_id == user_id,
            )
        )
        notif = result.scalar_one_or_none()
        if notif is None:
            raise NotFoundError("Notification", str(notif_id))
        if notif.read_at is None:
            notif.read_at = _utcnow()
            await self.session.flush()
        return notif

    async def mark_all_read(self, user_id: UUID) -> int:
        """全部已读，返回影响行数。"""
        result = await self.session.execute(
            update(Notification)
            .where(
                Notification.recipient_id == user_id,
                Notification.read_at.is_(None),
            )
            .values(read_at=_utcnow())
            .execution_options(synchronize_session=False)
        )
        return int(result.rowcount or 0)
