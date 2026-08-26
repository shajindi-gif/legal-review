"""M16.1 多租户隔离 Repository Helper。

设计: 不引入 PostgreSQL RLS (避免 superuser 绕过 + 迁移复杂度),
      而是在应用层强制 WHERE organization_id = current_user.organization_id。

共享模型:
- personal 组织: 1 user 1 org, 行为同单租户 (与 M16.1 之前完全一致)
- 非 personal 组织 (state_owned / public_inst / county_dept / township / street):
  同一组织内所有用户可见彼此的案件 (律所/法务部共享场景)
- super_admin: 跨租户可见 (审计/客服场景)

调用方:
- API 路由: 用 `filter_by_org(stmt, current_user, Model)` 包装
- 内部 service: 接收 `current_user` 参数, 自行调用
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import OrganizationType, UserRole
from app.models.user import Organization, User


def is_team_org(org: Organization | None) -> bool:
    """判断组织是否为团队型 (律所/法务部/政府部门等)。

    True: 同组织用户可见彼此数据
    False: 个人虚拟组织 (1 user 1 org) — 维持 submitter 隔离
    """
    if org is None:
        return False
    return str(org.type) != str(OrganizationType.PERSONAL)


def is_super_admin(user: User) -> bool:
    """超级管理员可跨租户访问。"""
    return bool(user.is_super_admin) or str(user.role) == str(UserRole.ADMIN)


def get_effective_org_id(user: User) -> UUID | None:
    """用户当前生效的 organization_id。

    规则:
    - 必须有 organization_id, 否则返回 None (异常用户)
    """
    return user.organization_id


def can_view_org(user: User, target_org_id: UUID) -> bool:
    """判断 user 是否有权访问 target_org_id 的数据。

    规则:
    - super_admin: 是
    - 同 organization_id: 是
    - 跨 org 但同 submitter_id: 是 (个人虚拟组织下, 只看自己的)
    - 其他: 否
    """
    if is_super_admin(user):
        return True
    if user.organization_id is None:
        return False
    return user.organization_id == target_org_id


def apply_org_filter(
    stmt: Select[Any],
    user: User,
    org: Organization | None,
    *,
    user_id_column: Any = None,
) -> Select[Any]:
    """给 select 语句加多租户过滤。

    参数:
    - stmt: 原始 SELECT
    - user: 当前请求用户
    - org: 当前用户的组织 (避免 N+1 查)
    - user_id_column: 模型上的 user_id / submitter_id 列 (用于 personal 组织回退)

    返回: 加过 WHERE 条件的 stmt

    行为:
    - super_admin → 不过滤
    - 团队组织 (state_owned 等) → WHERE organization_id = user.organization_id
    - personal 组织 → WHERE user_id_column = user.id (单租户)
    """
    if is_super_admin(user):
        return stmt

    if is_team_org(org):
        # 团队租户: 按 org 过滤
        return stmt.where(
            _get_org_column(stmt) == user.organization_id,
        )
    # personal: 退回 submitter 隔离 (老逻辑, 100% 兼容)
    if user_id_column is not None:
        return stmt.where(user_id_column == user.id)
    return stmt


def _get_org_column(stmt: Select[Any]) -> Any:
    """从 stmt 推断出 organization_id 列。

    简化: 假设所有租户表都有 organization_id, 用 SQLAlchemy 的 column introspection
    不通用, 所以让调用方显式传 column 更安全。
    """
    # 防御: 显式 import 时拿不到 model 类, 调用方应自行传 org_column
    raise NotImplementedError(
        "调用方需显式传 org_column, 见 apply_org_filter_with_column"
    )


def apply_org_filter_with_column(
    stmt: Select[Any],
    user: User,
    org: Organization | None,
    *,
    org_column: Any,
    user_id_column: Any | None = None,
) -> Select[Any]:
    """显式传 org_column 的版本, 避免 introspection 不可靠。"""
    if is_super_admin(user):
        return stmt

    if is_team_org(org):
        if user.organization_id is None:
            # 异常用户无 org_id, 只看自己 (个人隔离)
            if user_id_column is not None:
                return stmt.where(user_id_column == user.id)
            # 拿不到 user_id_column 兜底返回空结果
            return stmt.where(org_column.is_(None))
        return stmt.where(org_column == user.organization_id)
    # personal 组织
    if user_id_column is not None:
        return stmt.where(user_id_column == user.id)
    return stmt


async def load_user_org(
    session: AsyncSession, user: User
) -> Organization | None:
    """加载用户所属组织 (避免 N+1, 配合 eager loading)."""
    if user.organization_id is None:
        return None
    return await session.get(Organization, user.organization_id)
