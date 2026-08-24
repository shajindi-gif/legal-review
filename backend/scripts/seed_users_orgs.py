"""预置系统默认用户与单位（鉴权前阶段的兜底）。

背景：documents.upload API 在未提供 X-Submitter-User-Id / X-Submitter-Org-Id 时，
原逻辑随机生成 UUID，触发 review_tasks.submitter_id 外键约束失败。

本脚本幂等插入：
- 1 个名为 "系统默认送审单位" 的 Organization（type=public_inst）
- 1 个名为 "system" 的 User（role=submitter），归属上述单位

API 侧改为：header 缺失时查询 username='system' 的用户兜底。
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.constants import OrganizationType, UserRole, UserStatus
from app.core.logging import get_logger
from app.db.session import get_session_factory
from app.models.user import Organization, User

logger = get_logger("seed.users_orgs")

SYSTEM_USERNAME = "system"
SYSTEM_ORG_NAME = "系统默认送审单位"


async def seed() -> None:
    factory = get_session_factory()
    async with factory() as session:
        # 1. Organization
        org_result = await session.execute(
            select(Organization).where(Organization.name == SYSTEM_ORG_NAME)
        )
        org = org_result.scalar_one_or_none()
        if org is None:
            org = Organization(
                id=uuid4(),
                name=SYSTEM_ORG_NAME,
                type=OrganizationType.PUBLIC_INST,
                status="active",
            )
            session.add(org)
            try:
                await session.flush()
                logger.info("org_created", org_id=str(org.id), name=org.name)
            except IntegrityError:
                await session.rollback()
                org_result = await session.execute(
                    select(Organization).where(Organization.name == SYSTEM_ORG_NAME)
                )
                org = org_result.scalar_one()

        # 2. User
        user_result = await session.execute(
            select(User).where(User.username == SYSTEM_USERNAME)
        )
        user = user_result.scalar_one_or_none()
        if user is None:
            user = User(
                id=uuid4(),
                username=SYSTEM_USERNAME,
                real_name="系统默认送审人",
                email=None,
                phone=None,
                password_hash="!",  # 禁止登录
                role=UserRole.SUBMITTER,
                organization_id=org.id,
                status=UserStatus.ACTIVE,
            )
            session.add(user)
            try:
                await session.flush()
                logger.info("user_created", user_id=str(user.id), username=user.username)
            except IntegrityError:
                await session.rollback()
                user_result = await session.execute(
                    select(User).where(User.username == SYSTEM_USERNAME)
                )
                user = user_result.scalar_one()

        await session.commit()
        print(
            f"\n[seed_users_orgs] OK\n"
            f"  organization_id = {user.organization_id}\n"
            f"  user_id         = {user.id}\n"
            f"  username        = {user.username}\n"
        )


if __name__ == "__main__":
    asyncio.run(seed())
