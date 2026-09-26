"""POC 一键启动：建管理员账号 + 默认单位 + Enterprise 无限配额 + 示例文件上传。

目标：1 个司法局客户 30 分钟内能登录 + 跑通 1 次完整审查。

用法（开发环境，DB 已 migrate 过）:
    cd backend
    .venv/bin/python scripts/seed_poc.py

产物：
- organization: POC 客户单位（id 打印到 stdout）
- admin user:   username=poc_admin / password=Poc@2026（首次登录后请改）
- 配额：Enterprise 无限（quota_daily=-1）
- 示例文件：test_data/sample_normative_doc.txt 已存在于文件系统，运行时打印 API 调用说明
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import select

from app.core.constants import (
    OrganizationType,
    PlanTier,
    UserRole,
    UserStatus,
)
from app.core.logging import get_logger
from app.db.session import get_session_factory
from app.models.user import Organization, User, UserPlan
from app.services.auth_service import hash_password

logger = get_logger("seed.poc")

POC_ORG_NAME = "POC 客户单位"
POC_ADMIN_USERNAME = "poc_admin"
POC_ADMIN_PASSWORD = "Poc@2026"
POC_ADMIN_REAL_NAME = "POC 管理员"


async def seed() -> None:
    factory = get_session_factory()
    async with factory() as session:
        # 1) 单位（team-style 团队型 → 客户后续加多账号时共用数据）
        org_result = await session.execute(
            select(Organization).where(Organization.name == POC_ORG_NAME)
        )
        org = org_result.scalar_one_or_none()
        if org is None:
            org = Organization(
                id=uuid4(),
                name=POC_ORG_NAME,
                type=OrganizationType.PUBLIC_INST,
                status="active",
            )
            session.add(org)
            await session.flush()
            logger.info("poc_org_created", org_id=str(org.id))

        # 2) 管理员用户
        user_result = await session.execute(
            select(User).where(User.username == POC_ADMIN_USERNAME)
        )
        user = user_result.scalar_one_or_none()
        if user is None:
            user = User(
                id=uuid4(),
                username=POC_ADMIN_USERNAME,
                real_name=POC_ADMIN_REAL_NAME,
                email="poc_admin@example.com",
                phone=None,
                password_hash=hash_password(POC_ADMIN_PASSWORD),
                role=UserRole.ADMIN,
                company=POC_ORG_NAME,
                organization_id=org.id,
                status=UserStatus.ACTIVE,
                is_super_admin=True,  # POC 阶段全权；正式上线后改 false
                agreed_terms_at=None,  # 首次登录走 onboarding
            )
            session.add(user)
            await session.flush()
            logger.info("poc_admin_created", user_id=str(user.id))
        else:
            # 幂等更新：保证密码是最新 + 角色是 admin
            user.password_hash = hash_password(POC_ADMIN_PASSWORD)
            user.role = UserRole.ADMIN
            user.is_super_admin = True
            user.status = UserStatus.ACTIVE
            user.organization_id = org.id
            await session.flush()
            logger.info("poc_admin_updated", user_id=str(user.id))

        # 3) Enterprise 套餐：quota_daily=-1 (不限)
        plan_result = await session.execute(
            select(UserPlan).where(UserPlan.user_id == user.id)
        )
        plan = plan_result.scalar_one_or_none()
        if plan is None:
            plan = UserPlan(
                id=uuid4(),
                user_id=user.id,
                tier=PlanTier.ENTERPRISE,
                quota_daily=-1,  # 不限
                used_today=0,
                period_days=30,
            )
            session.add(plan)
            await session.flush()
            logger.info("poc_plan_created", tier="enterprise")
        else:
            plan.tier = PlanTier.ENTERPRISE
            plan.quota_daily = -1
            plan.status = "active"
            await session.flush()
            logger.info("poc_plan_updated", tier="enterprise")

        await session.commit()

        print(
            f"\n[POC OK]\n"
            f"  organization_id   = {org.id}\n"
            f"  user_id           = {user.id}\n"
            f"  username          = {POC_ADMIN_USERNAME}\n"
            f"  password          = {POC_ADMIN_PASSWORD}\n"
            f"  plan              = enterprise (unlimited)\n"
            f"  is_super_admin    = True\n"
            f"\n[NEXT STEPS]\n"
            f"  1. 启动后端: docker compose -f deploy/docker-compose.prod.yml up -d backend\n"
            f"     或本地: cd backend && .venv/bin/uvicorn app.main:app --port 8002\n"
            f"  2. 跑法规 seed:\n"
            f"       EMBEDDING_BACKEND=api .venv/bin/python scripts/seed_laws.py\n"
            f"       EMBEDDING_BACKEND=api .venv/bin/python scripts/seed_henan_laws.py\n"
            f"  3. 登录 https://legalai86.com.cn  → 用 {POC_ADMIN_USERNAME} / {POC_ADMIN_PASSWORD}\n"
            f"  4. 上传 test_data/sample_normative_doc.txt 跑 1 次完整审查\n"
            f"  5. 验证: 11 节点全跑通,生成报告,evidences 引用真实法规\n"
        )


if __name__ == "__main__":
    asyncio.run(seed())
