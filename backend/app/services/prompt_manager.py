"""Prompt 版本管理服务 - Sprint 4 / FR-016 Prompt 版本化。

设计原则（来自 04_AGENT_GRAPH_DESIGN.md 第 6 节）：
1. YAML 文件作为版本源（DVC 数据版本化），DB 作为运行时激活层
2. 启动时加载 registry.yaml → 内存 active 版本表
3. 生产环境只允许 status='active' 的 Prompt
4. 任何变更必须先过 golden_dataset 评测（通过率 ≥ min_eval_pass_rate）
5. 旧版本状态置为 deprecated，可回滚
6. 未在 registry 注册的 prompt_key 禁止调用（硬约束）

加载优先级：DB active > YAML active_version > YAML 文件
渲染：Jinja2 严格模式（缺失变量直接报错，避免静默生成空值）
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, StrictUndefined
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import PromptStatus
from app.core.errors import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.platform import Prompt

logger = get_logger("services.prompt_manager")

# ============== Prompt 目录定位 ==============
PROMPTS_DIR: Path = Path(__file__).resolve().parent.parent / "agent" / "prompts"
REGISTRY_PATH: Path = PROMPTS_DIR / "registry.yaml"


# ============== 数据结构 ==============
class PromptSpec:
    """Prompt 规格（不可变，运行时只读）。"""

    def __init__(
        self,
        *,
        prompt_key: str,
        version: str,
        template: str,
        variables: list[dict[str, Any]],
        model_name: str,
        temperature: float,
        status: str = PromptStatus.ACTIVE.value,
        min_eval_pass_rate: float = 0.9,
        eval_pass_rate: float | None = None,
        model_tier: str = "strong",  # strong|balanced|flash|reasoner
    ) -> None:
        self.prompt_key = prompt_key
        self.version = version
        self.template = template
        self.variables = variables
        self.model_name = model_name
        self.temperature = float(temperature)
        self.status = status
        self.min_eval_pass_rate = float(min_eval_pass_rate)
        self.eval_pass_rate = (
            float(eval_pass_rate) if eval_pass_rate is not None else None
        )
        self.model_tier = model_tier

    def __repr__(self) -> str:
        return (
            f"PromptSpec(key={self.prompt_key}, version={self.version}, "
            f"status={self.status}, tier={self.model_tier})"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt_key": self.prompt_key,
            "version": self.version,
            "template": self.template,
            "variables": self.variables,
            "model_name": self.model_name,
            "temperature": self.temperature,
            "status": self.status,
            "min_eval_pass_rate": self.min_eval_pass_rate,
            "eval_pass_rate": self.eval_pass_rate,
            "model_tier": self.model_tier,
        }


# ============== Jinja2 渲染环境 ==============
_jinja_env = Environment(
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=True,
    autoescape=False,
)


# ============== Prompt Manager ==============
class PromptManager:
    """Prompt 版本管理器（单例）。

    生命周期：
    1. 应用启动：load_registry() 加载 registry.yaml 到内存
    2. 节点调用：get_active(key) 获取 active 版本 → render() 渲染
    3. 评估门控：activate(key, version, eval_pass_rate) 激活新版本
    4. 回滚：deactivate(key, version) 置回 deprecated

    内存缓存：
    - _registry: dict[prompt_key, dict]  # registry.yaml 条目
    - _active_cache: dict[prompt_key, PromptSpec]  # 已加载的 active 版本
    """

    def __init__(self, prompts_dir: Path | None = None) -> None:
        self._prompts_dir = prompts_dir or PROMPTS_DIR
        self._registry_path = self._prompts_dir / "registry.yaml"
        self._registry: dict[str, dict[str, Any]] = {}
        self._active_cache: dict[str, PromptSpec] = {}
        self._loaded = False

    # ---------- 启动加载 ----------
    def load_registry(self) -> None:
        """加载 registry.yaml 到内存（启动时调用）。

        失败策略：文件不存在则空 registry（测试场景），
        YAML 解析失败则抛 ValidationError（启动期 fail-fast）。
        """
        if not self._registry_path.exists():
            logger.warning(
                "prompt_registry_missing", path=str(self._registry_path)
            )
            self._loaded = True
            return

        try:
            with self._registry_path.open(encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            raise ValidationError(
                f"registry.yaml 解析失败: {e}"
            ) from e

        entries = data.get("prompts", []) if isinstance(data, dict) else []
        self._registry = {}
        for entry in entries:
            key = entry.get("prompt_key")
            if not key:
                continue
            self._registry[key] = entry

        self._loaded = True
        logger.info(
            "prompt_registry_loaded",
            count=len(self._registry),
            path=str(self._registry_path),
        )

    def _ensure_loaded(self) -> None:
        """懒加载：首次访问时加载 registry。"""
        if not self._loaded:
            self.load_registry()

    # ---------- 查询 ----------
    def list_keys(self) -> list[str]:
        """列出全部已注册 prompt_key。"""
        self._ensure_loaded()
        return sorted(self._registry.keys())

    def get_registry_entry(self, prompt_key: str) -> dict[str, Any]:
        """获取 registry.yaml 中的原始条目。"""
        self._ensure_loaded()
        entry = self._registry.get(prompt_key)
        if entry is None:
            raise NotFoundError("PromptKey", prompt_key)
        return entry

    def get_active_version(self, prompt_key: str) -> str:
        """获取当前激活版本号。"""
        entry = self.get_registry_entry(prompt_key)
        version = entry.get("active_version")
        if not version:
            raise ValidationError(
                f"prompt_key={prompt_key} 未配置 active_version"
            )
        return version

    # ---------- 加载 PromptSpec ----------
    def get_active(self, prompt_key: str) -> PromptSpec:
        """获取当前 active 版本的 PromptSpec（带缓存）。

        加载顺序：
        1. 内存缓存命中 → 直接返回
        2. 从 YAML 文件加载（按 registry.active_version）
        3. 失败则抛 NotFoundError
        """
        self._ensure_loaded()

        cached = self._active_cache.get(prompt_key)
        if cached is not None:
            return cached

        version = self.get_active_version(prompt_key)
        spec = self._load_from_yaml(prompt_key, version)
        self._active_cache[prompt_key] = spec
        return spec

    def _load_from_yaml(self, prompt_key: str, version: str) -> PromptSpec:
        """从 YAML 文件加载 PromptSpec。"""
        file_path = self._prompts_dir / prompt_key / f"{version}.yaml"
        if not file_path.exists():
            raise NotFoundError(
                "PromptYAML",
                f"{prompt_key}/{version}.yaml at {file_path}",
            )

        try:
            with file_path.open(encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            raise ValidationError(
                f"Prompt YAML 解析失败 {prompt_key}@{version}: {e}"
            ) from e

        # 与 registry 合并（registry 作为默认值的来源）
        registry_entry = self._registry.get(prompt_key, {})

        template = data.get("template")
        if not template:
            raise ValidationError(
                f"Prompt {prompt_key}@{version} 缺少 template 字段"
            )

        return PromptSpec(
            prompt_key=prompt_key,
            version=version,
            template=template,
            variables=data.get("variables", []),
            model_name=(
                data.get("model_name")
                or registry_entry.get("model_name", "deepseek-v4-flash")
            ),
            temperature=data.get("temperature", registry_entry.get("temperature", 0.2)),
            status=PromptStatus.ACTIVE.value,
            min_eval_pass_rate=registry_entry.get("min_eval_pass_rate", 0.9),
            model_tier=registry_entry.get("model_tier", "strong"),
        )

    def list_versions(self, prompt_key: str) -> list[str]:
        """列出 prompt_key 的全部本地版本（按文件名扫描）。"""
        dir_path = self._prompts_dir / prompt_key
        if not dir_path.exists():
            return []
        versions = []
        for p in dir_path.glob("*.yaml"):
            stem = p.stem  # v1.0.0
            versions.append(stem)
        return sorted(versions)

    # ---------- 渲染 ----------
    def render(self, prompt_key: str, variables: dict[str, Any]) -> str:
        """渲染 Prompt 模板。

        硬约束：Jinja2 StrictUndefined，缺失变量直接报错。
        """
        spec = self.get_active(prompt_key)
        return self._render_template(spec, variables)

    def _render_template(self, spec: PromptSpec, variables: dict[str, Any]) -> str:
        """Jinja2 渲染（StrictUndefined）。"""
        # 校验必填变量
        self._validate_variables(spec, variables)

        try:
            template = _jinja_env.from_string(spec.template)
            return template.render(**variables)
        except Exception as e:
            raise ValidationError(
                f"Prompt 渲染失败 {spec.prompt_key}@{spec.version}: {e}"
            ) from e

    def _validate_variables(
        self, spec: PromptSpec, variables: dict[str, Any]
    ) -> None:
        """校验必填变量。"""
        missing: list[str] = []
        for var_def in spec.variables:
            name = var_def.get("name")
            required = var_def.get("required", False)
            if required and (name not in variables or variables[name] is None):
                missing.append(name)
        if missing:
            raise ValidationError(
                f"Prompt {spec.prompt_key}@{spec.version} 缺失必填变量: {missing}"
            )

    # ---------- DB 同步与激活 ----------
    async def sync_to_db(self, session: AsyncSession) -> int:
        """将 YAML 中的 active 版本同步到 prompts 表。

        启动时调用：保证 DB 与 YAML 一致。
        幂等：已存在则跳过，不存在则插入 status=active。
        """
        self._ensure_loaded()
        synced = 0
        for key, entry in self._registry.items():
            version = entry.get("active_version")
            if not version:
                continue

            # 查询是否已存在
            result = await session.execute(
                select(Prompt).where(
                    Prompt.prompt_key == key,
                    Prompt.version == version,
                )
            )
            existing = result.scalar_one_or_none()

            if existing is not None:
                # 已存在，更新状态为 active（如需要）
                if existing.status != PromptStatus.ACTIVE.value:
                    existing.status = PromptStatus.ACTIVE.value
                    existing.activated_at = datetime.utcnow()
                    await session.flush()
                    synced += 1
                continue

            # 不存在，从 YAML 加载并插入
            try:
                spec = self._load_from_yaml(key, version)
            except NotFoundError:
                logger.warning(
                    "prompt_yaml_missing_during_sync",
                    prompt_key=key, version=version,
                )
                continue

            new_prompt = Prompt(
                prompt_key=key,
                version=version,
                template=spec.template,
                variables={"vars": spec.variables},
                model_name=spec.model_name,
                temperature=spec.temperature,
                status=PromptStatus.ACTIVE.value,
                activated_at=datetime.utcnow(),
            )
            session.add(new_prompt)
            synced += 1

        await session.flush()
        logger.info("prompt_synced_to_db", count=synced)
        return synced

    async def activate(
        self,
        session: AsyncSession,
        prompt_key: str,
        version: str,
        eval_pass_rate: float,
    ) -> Prompt:
        """激活某版本（评估门控）。

        硬约束：
        - eval_pass_rate < min_eval_pass_rate 则拒绝激活
        - 激活前先将旧 active 版本置为 deprecated（保留可回滚）
        """
        entry = self.get_registry_entry(prompt_key)
        min_rate = float(entry.get("min_eval_pass_rate", 0.9))

        if eval_pass_rate < min_rate:
            raise ValidationError(
                f"Prompt {prompt_key}@{version} 评测通过率 {eval_pass_rate:.2%} "
                f"< 最低要求 {min_rate:.2%}，禁止激活（硬约束：未经评估 Prompt 禁合并）"
            )

        # 旧 active 置为 deprecated
        old_result = await session.execute(
            select(Prompt).where(
                Prompt.prompt_key == prompt_key,
                Prompt.status == PromptStatus.ACTIVE.value,
            )
        )
        old_active = old_result.scalar_one_or_none()
        if old_active is not None:
            old_active.status = PromptStatus.DEPRECATED.value

        # 新版本置为 active
        new_result = await session.execute(
            select(Prompt).where(
                Prompt.prompt_key == prompt_key,
                Prompt.version == version,
            )
        )
        prompt = new_result.scalar_one_or_none()
        if prompt is None:
            raise NotFoundError("Prompt", f"{prompt_key}@{version}")

        prompt.status = PromptStatus.ACTIVE.value
        prompt.eval_pass_rate = eval_pass_rate
        prompt.activated_at = datetime.utcnow()
        await session.flush()

        # 更新内存缓存
        self._active_cache.pop(prompt_key, None)
        self._registry[prompt_key]["active_version"] = version

        logger.info(
            "prompt_activated",
            prompt_key=prompt_key,
            version=version,
            eval_pass_rate=eval_pass_rate,
        )
        return prompt

    async def deactivate(
        self,
        session: AsyncSession,
        prompt_key: str,
        version: str,
    ) -> Prompt:
        """回滚：将版本置为 deprecated。"""
        result = await session.execute(
            select(Prompt).where(
                Prompt.prompt_key == prompt_key,
                Prompt.version == version,
            )
        )
        prompt = result.scalar_one_or_none()
        if prompt is None:
            raise NotFoundError("Prompt", f"{prompt_key}@{version}")

        prompt.status = PromptStatus.DEPRECATED.value
        await session.flush()

        # 清缓存
        self._active_cache.pop(prompt_key, None)

        logger.info(
            "prompt_deactivated", prompt_key=prompt_key, version=version
        )
        return prompt

    # ---------- 缓存管理 ----------
    def invalidate_cache(self, prompt_key: str | None = None) -> None:
        """清缓存（评估门控激活/回滚后调用）。"""
        if prompt_key is None:
            self._active_cache.clear()
        else:
            self._active_cache.pop(prompt_key, None)


# ============== 单例 ==============
_manager: PromptManager | None = None


def get_prompt_manager() -> PromptManager:
    """获取全局 PromptManager 单例。"""
    global _manager
    if _manager is None:
        _manager = PromptManager()
    return _manager
