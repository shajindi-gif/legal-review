"""配额服务 - Free/Pro/Enterprise 每日审查次数控制。

DB 兜底版（不依赖 Redis），按 UTC 日期重置 used_today。
Pro/Enterprise 配额为 -1（不限）。
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import PlanTier
from app.core.errors import QuotaExceededError
from app.models.user import UserPlan


class QuotaService:
    """用户审查配额管理。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create_plan(self, user_id: UUID) -> UserPlan:
        """获取用户套餐；不存在则创建 Free 兜底。"""
        plan = await self._session.scalar(
            select(UserPlan).where(UserPlan.user_id == user_id)
        )
        if plan is None:
            plan = UserPlan(
                user_id=user_id,
                tier=PlanTier.FREE,
                status="active",
                quota_daily=3,
                used_today=0,
                quota_reset_date=datetime.now(UTC).strftime("%Y-%m-%d"),
            )
            self._session.add(plan)
            await self._session.flush()
        return plan

    @staticmethod
    def _today_str() -> str:
        """当前 UTC 日期字符串。"""
        return datetime.now(UTC).strftime("%Y-%m-%d")

    def _maybe_reset(self, plan: UserPlan) -> bool:
        """跨天重置 used_today（就地修改）。返回是否发生了重置。"""
        today = self._today_str()
        if plan.quota_reset_date != today:
            plan.used_today = 0
            plan.quota_reset_date = today
            return True
        return False

    def is_unlimited(self, plan: UserPlan) -> bool:
        """Pro/Enterprise 不限次数。"""
        return plan.quota_daily < 0

    def remaining(self, plan: UserPlan) -> int:
        """剩余次数；不限时返回 -1。"""
        if self.is_unlimited(plan):
            return -1
        return max(0, plan.quota_daily - plan.used_today)

    async def check_quota(self, user_id: UUID) -> UserPlan:
        """检查配额；超限抛 QuotaExceededError。返回当前 plan。"""
        plan = await self.get_or_create_plan(user_id)
        self._maybe_reset(plan)
        if not self.is_unlimited(plan) and plan.used_today >= plan.quota_daily:
            msg = (
                f"今日审查次数已用尽（{plan.used_today}/{plan.quota_daily}），"
                f"请明日再试或升级套餐"
            )
            raise QuotaExceededError(msg)
        await self._session.flush()
        return plan

    async def consume(self, user_id: UUID) -> UserPlan:
        """消耗一次审查配额；超限抛异常。"""
        plan = await self.check_quota(user_id)
        if not self.is_unlimited(plan):
            plan.used_today += 1
            await self._session.flush()
        return plan

    async def get_status(self, user_id: UUID) -> dict:
        """获取配额状态摘要。"""
        plan = await self.get_or_create_plan(user_id)
        self._maybe_reset(plan)
        return {
            "tier": str(plan.tier),
            "quota_daily": plan.quota_daily,
            "used_today": plan.used_today,
            "remaining": self.remaining(plan),
            "unlimited": self.is_unlimited(plan),
            "reset_date": plan.quota_reset_date,
        }
