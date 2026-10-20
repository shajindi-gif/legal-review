"""规范性文件合法性审核规则包（PHASE 1-5）。

规则包是 **数据驱动的 YAML 清单**，按地域分层：
    国家通用规则包 / 上海市规则包 / 徐汇区定制规则包 / 其他地方规则包（可扩展）

每条规则明确（指令第六条硬约束）：
    law_basis(法律依据) / region(适用地区) / effective_date(生效时间) /
    condition(审核条件) / evidence_required(证据要求) / exception(例外条件) /
    risk_type(风险类型)

硬约束：
- 不得把某一地方性规范当成全国通用标准（因此按 region 分包）。
- 地方规则包上线前需法律专业人员审核：未审核通过时
  legal_review_status=pending_legal_review，报告必须提示"依据需人工复核"。
- 未核实字段一律留空（null），禁止编造法条编号与生效时间。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic import ValidationError as PydanticValidationError

from app.core.constants import GovReviewDimension, GovRiskLevel, GovRuleReviewStatus
from app.core.errors import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.schemas.gov_review import (
    GovRulePackRead,
    GovRuleRead,
    dimension_sort_key,
)

logger = get_logger("services.gov_rules")

GOV_RULES_DIR: Path = Path(__file__).resolve().parent.parent / "gov_rules"
REGISTRY_PATH: Path = GOV_RULES_DIR / "registry.yaml"

_VALID_DIMENSIONS: set[str] = {str(d) for d in GovReviewDimension}
_VALID_SEVERITIES: set[str] = {str(s) for s in GovRiskLevel}


class GovRule(BaseModel):
    """单条审核规则。"""

    rule_id: str
    dimension: str
    title: str
    risk_type: str
    severity: str
    law_basis: str
    law_basis_article: str | None = None
    region: str
    effective_date: str | None = None
    condition: str
    evidence_required: list[str] = Field(default_factory=list)
    exception: str | None = None
    source_url: str | None = None
    pending_fields: list[str] = Field(default_factory=list)


class GovRulePack(BaseModel):
    """审核规则包。"""

    pack_id: str
    name: str
    scope: str
    region: str
    description: str
    legal_review_status: str
    reviewed_by: str | None = None
    rules: list[GovRule] = Field(default_factory=list)


class GovRulePackManager:
    """规则包管理器（单例，启动时加载 registry.yaml）。"""

    def __init__(self, rules_dir: Path | None = None) -> None:
        self._dir = rules_dir or GOV_RULES_DIR
        self._packs: dict[str, GovRulePack] = {}
        self._loaded = False

    # ---------- 加载 ----------
    def load(self) -> None:
        registry = self._dir / "registry.yaml"
        if not registry.exists():
            logger.warning("gov_rules_registry_missing", path=str(registry))
            self._loaded = True
            return

        try:
            data = yaml.safe_load(registry.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as e:
            raise ValidationError(f"gov_rules registry.yaml 解析失败: {e}") from e

        entries = data.get("packs", []) if isinstance(data, dict) else []
        packs: dict[str, GovRulePack] = {}
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            pack_id = str(entry.get("pack_id") or "").strip()
            if not pack_id:
                continue
            packs[pack_id] = GovRulePack(
                pack_id=pack_id,
                name=str(entry.get("name") or pack_id),
                scope=str(entry.get("scope") or "national"),
                region=str(entry.get("region") or ""),
                description=str(entry.get("description") or ""),
                legal_review_status=str(
                    entry.get("legal_review_status")
                    or GovRuleReviewStatus.PENDING.value
                ),
                reviewed_by=entry.get("reviewed_by"),
                rules=self._load_rules(entry),
            )

        self._packs = packs
        self._loaded = True
        logger.info(
            "gov_rules_loaded",
            packs=len(packs),
            rules=sum(len(p.rules) for p in packs.values()),
        )

    def _load_rules(self, entry: dict[str, Any]) -> list[GovRule]:
        rules_file = entry.get("rules_file")
        if not rules_file:
            return []
        path = self._dir / str(rules_file)
        if not path.exists():
            raise ValidationError(
                f"规则包 {entry.get('pack_id')} 的 rules_file 不存在: {path}"
            )
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as e:
            raise ValidationError(f"规则文件解析失败 {path}: {e}") from e

        raw_rules = data.get("rules", []) if isinstance(data, dict) else []
        rules: list[GovRule] = []
        for raw in raw_rules:
            if not isinstance(raw, dict):
                continue
            try:
                rule = GovRule(**raw)
            except PydanticValidationError as e:
                raise ValidationError(f"规则字段非法 {path}: {e}") from e
            self._validate_rule(rule, path)
            rules.append(rule)
        return rules

    @staticmethod
    def _validate_rule(rule: GovRule, path: Path) -> None:
        if rule.dimension not in _VALID_DIMENSIONS:
            raise ValidationError(
                f"{path}: rule_id={rule.rule_id} 维度非法: {rule.dimension}"
            )
        if rule.severity not in _VALID_SEVERITIES:
            raise ValidationError(
                f"{path}: rule_id={rule.rule_id} 风险等级非法: {rule.severity}"
            )
        if not rule.condition.strip():
            raise ValidationError(
                f"{path}: rule_id={rule.rule_id} 缺少审核条件(condition)"
            )

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    # ---------- 查询 ----------
    def list_packs(self) -> list[GovRulePack]:
        """全部规则包：国家通用优先，其余按 pack_id 排序。"""
        self._ensure_loaded()
        return sorted(
            self._packs.values(),
            key=lambda p: (0 if p.scope == "national" else 1, p.pack_id),
        )

    def get_pack(self, pack_id: str) -> GovRulePack:
        self._ensure_loaded()
        pack = self._packs.get(pack_id)
        if pack is None:
            raise NotFoundError("GovRulePack", pack_id)
        return pack

    def resolve_for_region(self, region: str | None) -> list[GovRulePack]:
        """按地区解析适用的规则包集合。

        - 国家通用规则包恒选（作为全国适用基线）。
        - 地方规则包在 `region` 包含该包地区时选中
          （如 region="上海市徐汇区" 命中「上海市」与「徐汇区」两个包）。
        - region 为空时仅返回国家通用规则包。
        """
        self._ensure_loaded()
        target = (region or "").strip()
        selected: list[GovRulePack] = []
        for pack in self.list_packs():
            if pack.scope == "national":
                selected.append(pack)
                continue
            if target and pack.region and pack.region in target:
                selected.append(pack)
        return selected

    def rules_for_region(self, region: str | None) -> list[GovRule]:
        """按地区展开全部适用规则（已按维度排序）。"""
        rules: list[GovRule] = []
        for pack in self.resolve_for_region(region):
            rules.extend(pack.rules)
        return sorted(rules, key=lambda r: (dimension_sort_key(r.dimension), r.rule_id))


# ============== Schema 映射 ==============
def rule_to_read(rule: GovRule) -> GovRuleRead:
    from app.core.constants import GOV_DIMENSION_LABELS

    return GovRuleRead(
        rule_id=rule.rule_id,
        dimension=rule.dimension,
        dimension_label=GOV_DIMENSION_LABELS.get(rule.dimension, rule.dimension),
        title=rule.title,
        risk_type=rule.risk_type,
        severity=rule.severity,
        law_basis=rule.law_basis,
        law_basis_article=rule.law_basis_article,
        region=rule.region,
        effective_date=rule.effective_date,
        condition=rule.condition,
        evidence_required=list(rule.evidence_required),
        exception=rule.exception,
        source_url=rule.source_url,
        pending_fields=list(rule.pending_fields),
    )


def pack_to_read(pack: GovRulePack) -> GovRulePackRead:
    rules = sorted(
        pack.rules, key=lambda r: (dimension_sort_key(r.dimension), r.rule_id)
    )
    return GovRulePackRead(
        pack_id=pack.pack_id,
        name=pack.name,
        scope=pack.scope,
        region=pack.region,
        description=pack.description,
        legal_review_status=pack.legal_review_status,
        reviewed_by=pack.reviewed_by,
        rule_count=len(rules),
        rules=[rule_to_read(r) for r in rules],
    )


# ============== 单例 ==============
_manager: GovRulePackManager | None = None


def get_gov_rule_pack_manager() -> GovRulePackManager:
    """获取全局规则包管理器单例。"""
    global _manager
    if _manager is None:
        _manager = GovRulePackManager()
    return _manager


def reset_gov_rule_pack_manager() -> None:
    """重置单例（测试用）。"""
    global _manager
    _manager = None


__all__ = [
    "GOV_RULES_DIR",
    "REGISTRY_PATH",
    "GovRule",
    "GovRulePack",
    "GovRulePackManager",
    "get_gov_rule_pack_manager",
    "pack_to_read",
    "reset_gov_rule_pack_manager",
    "rule_to_read",
]
