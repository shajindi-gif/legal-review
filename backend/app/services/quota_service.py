"""配额服务 - Free/Pro/Enterprise 审查次数控制。

Free 套餐：累计 2 次免费体验（free_trial_used / free_trial_limit），
用尽后需升级（Pro/Enterprise 不限次数，quota_daily=-1）。
不再按 UTC 日期每日重置。
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import FREE_TRIAL_LIMIT, PlanTier
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
                quota_daily=FREE_TRIAL_LIMIT,
                used_today=0,
                free_trial_used=0,
                free_trial_limit=FREE_TRIAL_LIMIT,
            )
            self._session.add(plan)
            await self._session.flush()
        elif plan.free_trial_limit is None:
            # 历史记录回填默认上限
            plan.free_trial_limit = FREE_TRIAL_LIMIT
        return plan

    def is_unlimited(self, plan: UserPlan) -> bool:
        """Pro/Enterprise 不限次数。"""
        return str(plan.tier) in (PlanTier.PRO.value, PlanTier.ENTERPRISE.value)

    def _trial_limit(self, plan: UserPlan) -> int:
        """免费体验上限（Free 才有意义）。"""
        return plan.free_trial_limit if plan.free_trial_limit is not None else FREE_TRIAL_LIMIT

    def _trial_used(self, plan: UserPlan) -> int:
        """已用免费体验次数。"""
        return plan.free_trial_used or 0

    def remaining(self, plan: UserPlan) -> int:
        """剩余免费次数；不限时返回 -1。"""
        if self.is_unlimited(plan):
            return -1
        return max(0, self._trial_limit(plan) - self._trial_used(plan))

    async def check_quota(self, user_id: UUID) -> UserPlan:
        """检查配额；超限抛 QuotaExceededError。返回当前 plan。"""
        plan = await self.get_or_create_plan(user_id)
        if not self.is_unlimited(plan):
            used = self._trial_used(plan)
            limit = self._trial_limit(plan)
            if used >= limit:
                msg = (
                    f"免费体验次数已用尽（{used}/{limit}），"
                    f"请升级套餐继续使用"
                )
                raise QuotaExceededError(msg)
        await self._session.flush()
        return plan

    async def consume(self, user_id: UUID) -> UserPlan:
        """消耗一次审查配额；超限抛异常。"""
        plan = await self.check_quota(user_id)
        if not self.is_unlimited(plan):
            plan.free_trial_used = self._trial_used(plan) + 1
            await self._session.flush()
        return plan

    async def get_status(self, user_id: UUID) -> dict:
        """获取配额状态摘要。"""
        plan = await self.get_or_create_plan(user_id)
        unlimited = self.is_unlimited(plan)
        return {
            "tier": str(plan.tier),
            "quota_daily": plan.quota_daily,
            "used_today": plan.used_today,
            "free_trial_used": self._trial_used(plan),
            "free_trial_limit": self._trial_limit(plan),
            "remaining": self.remaining(plan),
            "unlimited": unlimited,
            "reset_date": plan.quota_reset_date,
        }