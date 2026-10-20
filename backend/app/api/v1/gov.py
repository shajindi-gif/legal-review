"""规范性文件合法性审核规则包 API（PHASE 1-5）。

仅提供规则包的查询/按地区解析；审核报告与交付物导出在 ``/tasks`` 下
（与既有工作流任务绑定，复用其多租户鉴权）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_user
from app.schemas.gov_review import GovRulePackRead
from app.services.core_auth_client import CorePrincipal
from app.services.gov_rules import get_gov_rule_pack_manager, pack_to_read

router = APIRouter(prefix="/gov", tags=["gov"])


@router.get("/rule-packs", response_model=list[GovRulePackRead])
async def list_rule_packs(
    _user: CorePrincipal = Depends(get_current_user),
) -> list[GovRulePackRead]:
    """列出全部审核规则包（国家通用 / 上海市 / 徐汇区 …）。"""
    manager = get_gov_rule_pack_manager()
    return [pack_to_read(p) for p in manager.list_packs()]


@router.get("/rule-packs/resolve", response_model=list[GovRulePackRead])
async def resolve_rule_packs(
    region: str | None = Query(
        default=None, description="适用区域，如 上海市徐汇区（缺省仅返回国家通用规则包）"
    ),
    _user: CorePrincipal = Depends(get_current_user),
) -> list[GovRulePackRead]:
    """按地区解析适用的规则包（国家通用恒选 + 命中的地方规则包）。"""
    manager = get_gov_rule_pack_manager()
    return [pack_to_read(p) for p in manager.resolve_for_region(region)]


@router.get("/rule-packs/{pack_id}", response_model=GovRulePackRead)
async def get_rule_pack(
    pack_id: str,
    _user: CorePrincipal = Depends(get_current_user),
) -> GovRulePackRead:
    """查询单个规则包详情（含全部规则）。"""
    return pack_to_read(get_gov_rule_pack_manager().get_pack(pack_id))
