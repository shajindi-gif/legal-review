"""用户反馈中心 Service（UI-M11）。

提供 5 个方法：
- create：提交一条反馈（前端 FeedbackBar 调用）
- list_for_user：分页查询当前用户的反馈
- get_for_user：按 id 查单条（强制 user 隔离）
- mark_closed：用户关闭/已读
- list_for_admin：管理端全量查询 + 状态筛 + 更新 status

设计要点：
- 用户侧强制 user_id 隔离，越权访问抛 NotFoundError
- 用户只能关闭（closed_at），不能改 status / admin_reply
- admin 端权限校验交给路由层（要求 user.role == 'admin'）
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationError
from app.models.user_feedback import UserFeedback
from app.schemas.user_feedback import UserFeedbackCreate


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class UserFeedbackService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ============== 写入 ==============
    async def create(
        self,
        *,
        user_id: UUID,
        payload: UserFeedbackCreate,
    ) -> UserFeedback:
        """提交一条用户反馈。

        极简校验：vote 必须 ∈ up/down/neutral（schema 已校验）；
        comment 长度 schema 已校验。
        """
        record = UserFeedback(
            user_id=user_id,
            target_kind=payload.target_kind,
            target_id=payload.target_id,
            target_label=payload.target_label,
            vote=payload.vote,
            comment=payload.comment,
            status="open",
            context=payload.context,
        )
        self.session.add(record)
        await self.session.flush()
        return record

    # ============== 用户侧 ==============
    async def list_for_user(
        self,
        *,
        user_id: UUID,
        status: str | None = None,
        target_kind: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[UserFeedback], int]:
        """分页查询某用户的反馈。"""
        if page < 1:
            raise ValidationError("page 必须 ≥ 1")
        if page_size < 1 or page_size > 100:
            raise ValidationError("page_size 必须在 [1, 100]")

        stmt = select(UserFeedback).where(UserFeedback.user_id == user_id)
        count_stmt = select(func.count()).select_from(UserFeedback).where(
            UserFeedback.user_id == user_id
        )
        if status:
            stmt = stmt.where(UserFeedback.status == status)
            count_stmt = count_stmt.where(UserFeedback.status == status)
        if target_kind:
            stmt = stmt.where(UserFeedback.target_kind == target_kind)
            count_stmt = count_stmt.where(UserFeedback.target_kind == target_kind)

        total = (await self.session.execute(count_stmt)).scalar_one() or 0
        stmt = (
            stmt.order_by(desc(UserFeedback.created_at))
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), int(total)

    async def get_for_user(
        self,
        *,
        user_id: UUID,
        feedback_id: UUID,
    ) -> UserFeedback:
        """按 id 取单条，越权抛 NotFoundError。"""
        stmt = select(UserFeedback).where(
            UserFeedback.id == feedback_id,
            UserFeedback.user_id == user_id,
        )
        record = (await self.session.execute(stmt)).scalar_one_or_none()
        if record is None:
            raise NotFoundError(f"反馈不存在或无访问权限: {feedback_id}")
        return record

    async def mark_closed(
        self,
        *,
        user_id: UUID,
        feedback_id: UUID,
    ) -> UserFeedback:
        """用户主动关闭（已读/已处理）。幂等：再次关闭不报错。"""
        record = await self.get_for_user(user_id=user_id, feedback_id=feedback_id)
        if record.closed_at is None:
            record.closed_at = _utcnow()
            await self.session.flush()
        return record

    async def summary_for_user(self, *, user_id: UUID) -> dict:
        """当前用户的反馈概览（按 status 计数）。"""
        rows = await self.session.execute(
            select(UserFeedback.status, func.count())
            .where(UserFeedback.user_id == user_id)
            .group_by(UserFeedback.status)
        )
        counts: dict[str, int] = {}
        total = 0
        for status, count in rows.all():
            counts[status] = int(count)
            total += int(count)
        return {
            "total": total,
            "by_status": counts,
        }

    # ============== 管理员侧 ==============
    async def list_for_admin(
        self,
        *,
        status: str | None = None,
        target_kind: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[UserFeedback], int]:
        """管理员全量查询。"""
        if page < 1:
            raise ValidationError("page 必须 ≥ 1")
        if page_size < 1 or page_size > 200:
            raise ValidationError("page_size 必须在 [1, 200]")

        stmt = select(UserFeedback)
        count_stmt = select(func.count()).select_from(UserFeedback)
        if status:
            stmt = stmt.where(UserFeedback.status == status)
            count_stmt = count_stmt.where(UserFeedback.status == status)
        if target_kind:
            stmt = stmt.where(UserFeedback.target_kind == target_kind)
            count_stmt = count_stmt.where(UserFeedback.target_kind == target_kind)

        total = (await self.session.execute(count_stmt)).scalar_one() or 0
        stmt = (
            stmt.order_by(desc(UserFeedback.created_at))
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), int(total)

    async def admin_update(
        self,
        *,
        feedback_id: UUID,
        status: str | None = None,
        admin_reply: str | None = None,
    ) -> UserFeedback:
        """管理员更新 status / admin_reply。status 必须 ∈ 4 状态之一。"""
        valid_status = {"open", "triaged", "resolved", "wontfix"}
        if status is not None and status not in valid_status:
            raise ValidationError(
                f"status 必须是 {sorted(valid_status)} 之一，收到 {status!r}"
            )
        if admin_reply is not None and len(admin_reply) > 1000:
            raise ValidationError("admin_reply 不能超过 1000 字符")

        stmt = select(UserFeedback).where(UserFeedback.id == feedback_id)
        record = (await self.session.execute(stmt)).scalar_one_or_none()
        if record is None:
            raise NotFoundError(f"反馈不存在: {feedback_id}")

        if status is not None:
            record.status = status
        if admin_reply is not None:
            record.admin_reply = admin_reply
        await self.session.flush()
        return record

    # ============== 统计（admin dashboard 用） ==============
    async def summary(self) -> dict:
        """管理员概览：各 status 计数 + 总数。"""
        rows = await self.session.execute(
            select(UserFeedback.status, func.count())
            .group_by(UserFeedback.status)
        )
        counts: dict[str, int] = {}
        total = 0
        for status, count in rows.all():
            counts[status] = int(count)
            total += int(count)
        return {
            "total": total,
            "by_status": counts,
        }
