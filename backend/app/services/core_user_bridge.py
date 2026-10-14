"""Strangler 双跑期：Core 用户 → legal-review 本地 users 表的按需映射（lazy provisioning）。

背景
----
Phase 4 Pilot 把鉴权（register/login/me）切到了 yance-core（8200），Core 是 user_id / tenant_id
的权威源。但 legal-review 的业务层（documents / tasks / quota / audit 等）仍然依赖旧库
`users` / `organizations` / `user_plans` 表的 FK 约束。

如果不把 Core 用户按需补齐到本地表，每次访问都会撞 FK 报错（典型 500：
``user_plans_user_id_fkey``）。

策略
----
读路径优先尝试命中本地表，未命中时按 CorePrincipal 兜底建一条「影子记录」：
- 1 个 personal ``Organization``（id = CorePrincipal.tenant_id，便于反查）
- 1 个 ``User`` 行（id = CorePrincipal.id，沿用 Core 派发的 user_id）
- 1 个 ``UserPlan``（free / 3 次/日，由 QuotaService 自动建）

幂等性
----
所有 INSERT 都先 SELECT 检查，重复调用是 no-op。`ON CONFLICT DO NOTHING` 兜底并发。

不替换 / 不替代
----
这是 Strangler 双跑期兼容垫片，不是迁移产物。Core Auth 完整接管后，
本模块可整段删除（见 Strangler Phase 5 计划）。
"""
from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import OrganizationType, UserRole, UserStatus
from app.models.user import Organization, User
from app.services.core_auth_client import CorePrincipal

_log = logging.getLogger(__name__)


def _core_role_to_local_role(core_role: str) -> str:
    """Core userrole enum → legal-review UserRole。

    Core: owner / admin / member / viewer
    legal-review: submitter / reviewer / supervisor / admin / librarian
    映射规则：
    - owner / admin → admin（最高权限）
    - member → submitter（默认送审人）
    - viewer → submitter（只读用户也能送审）
    """
    r = core_role.lower()
    if r in ("owner", "admin"):
        return UserRole.ADMIN.value
    return UserRole.SUBMITTER.value


def _local_username_from_email(email: str | None) -> str:
    """从 email 派生合法 username。Core 暂无 username 字段。"""
    if not email:
        return "core-user"
    local = email.split("@")[0].lower()
    return local[:64] or "core-user"


def _org_name_from_principal(p: CorePrincipal) -> str:
    """从 CorePrincipal 派生 organization 显示名。"""
    base = p.company or p.real_name or p.username or p.email or "Core User"
    return f"{base} 工作台"[:128]


async def _ensure_personal_org(
    session: AsyncSession, principal: CorePrincipal
) -> UUID:
    """确保 personal Organization 存在；返回其 id（= CorePrincipal.tenant_id）。

    映射规则：Core tenant_id 直接复用为 local Organization.id，
    这样 legal-review 端可以用同一 UUID 在 Core / 本地两侧互查。
    """
    org_id = principal.tenant_id
    if org_id is None:
        raise RuntimeError(
            "Core principal is missing tenant_id; cannot ensure personal organization"
        )
    existing = await session.get(Organization, org_id)
    if existing is not None:
        return org_id

    # PG 级 ON CONFLICT DO NOTHING，避免和并发请求竞争
    stmt = (
        pg_insert(Organization)
        .values(
            id=org_id,
            name=_org_name_from_principal(principal),
            type=OrganizationType.PERSONAL.value,
            parent_id=None,
            region_code=None,
            status="active",
        )
        .on_conflict_do_nothing(index_elements=["id"])
    )
    await session.execute(stmt)
    # 重新读一次拿 ORM 对象（避免 async session 缓存问题）
    result = await session.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if org is None:
        # 极小概率并发丢失，回退用 SELECT FOR UPDATE 模式重新创建
        _log.warning("personal_org_retry org_id=%s", org_id)
        result = await session.execute(
            select(Organization).where(Organization.id == org_id)
        )
        org = result.scalar_one_or_none()
        if org is None:
            raise RuntimeError(
                f"failed to ensure personal organization {org_id} for Core user"
            )
    return org_id


async def _ensure_local_user(
    session: AsyncSession, principal: CorePrincipal, org_id: UUID
) -> User:
    """确保本地 users 表存在 CorePrincipal 对应的影子用户。

    关键约束：
    - id 必须等于 CorePrincipal.id（否则 FK 关系全断）
    - username/email 唯一约束需要兜底冲突
    - password_hash 用哨兵值 ``!core-bridge!``（不可登录，Core 是权威源）
    """
    existing = await session.get(User, principal.id)
    if existing is not None:
        return existing

    username = _local_username_from_email(principal.email)
    # username 在极少数 Core email 重复 / local 历史 username 冲突时需要 fallback
    for attempt in range(5):
        candidate = username if attempt == 0 else f"{username}-{attempt}"
        try:
            stmt = (
                pg_insert(User)
                .values(
                    id=principal.id,
                    username=candidate,
                    real_name=principal.real_name or principal.username or "Core User",
                    email=principal.email,
                    phone=None,
                    password_hash="!core-bridge!",
                    role=_core_role_to_local_role(principal.role),
                    company=principal.company,
                    organization_id=org_id,
                    status=UserStatus.ACTIVE.value,
                    locale="zh-CN",
                    timezone="Asia/Shanghai",
                    is_super_admin=principal.is_super_admin,
                )
                .on_conflict_do_nothing(index_elements=["id"])
            )
            await session.execute(stmt)
            break
        except IntegrityError as exc:
            # 命中 username/email 唯一冲突 → 改 candidate 重试
            await session.rollback()
            _log.info(
                "local_user_username_conflict_retry candidate=%s err=%s",
                candidate,
                str(exc)[:120],
            )
            continue

    # 重新读拿 ORM 对象
    result = await session.execute(select(User).where(User.id == principal.id))
    user = result.scalar_one_or_none()
    if user is None:
        raise RuntimeError(
            f"failed to ensure local user {principal.id} for Core principal"
        )
    return user


async def ensure_local_user_for_core_principal(
    session: AsyncSession, principal: CorePrincipal
) -> User:
    """Strangler 双跑期入口：业务层拿到 CorePrincipal 后调用一次。

    行为：
    - 本地 users 已有记录 → 直接返回（O(1) hit）
    - 没有 → 1 个 SELECT 确认 → INSERT personal org + INSERT user（INSERT 完用户已有 plan）

    调用方约定：
    - 当前请求的 db session 必须是写入 session（持有事务）
    - 该函数不 commit，调用方负责 commit/rollback
    """
    # 命中检查
    hit = await session.get(User, principal.id)
    if hit is not None:
        return hit

    # 兜底创建
    org_id = await _ensure_personal_org(session, principal)
    user = await _ensure_local_user(session, principal, org_id)
    _log.info(
        "core_user_bridged_to_local user_id=%s tenant_id=%s org_id=%s email=%s",
        principal.id,
        principal.tenant_id,
        org_id,
        principal.email,
    )
    return user
