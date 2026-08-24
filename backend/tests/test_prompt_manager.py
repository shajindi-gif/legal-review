"""Prompt 版本管理服务测试 - Sprint 4 / FR-016 Prompt 版本化。

覆盖：
- registry 加载（load_registry）
- get_active_version / get_active / list_keys / list_versions
- render Jinja2 渲染 + 必填变量校验
- 缺失变量报错（StrictUndefined）
- _load_from_yaml 文件不存在
- activate 评估门控（通过率 < 最低要求则拒绝）
- activate 成功（旧版本 deprecated）
- deactivate 回滚
- sync_to_db 同步到 DB
- 未注册 prompt_key 禁止调用（硬约束）
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.constants import PromptStatus
from app.core.errors import NotFoundError, ValidationError
from app.services.prompt_manager import (
    PROMPTS_DIR,
    PromptManager,
    PromptSpec,
    get_prompt_manager,
)


# ============== registry 加载 ==============
def test_load_registry_loads_all_entries() -> None:
    """启动加载 registry.yaml → 内存 8 个 prompt_key。"""
    pm = PromptManager()
    pm.load_registry()

    keys = pm.list_keys()
    # 8 个核心 prompt
    expected = {
        "doc_classify",
        "legal_query",
        "authority_review",
        "procedure_review",
        "content_review",
        "risk_assessment",
        "evidence_verify",
        "report_generation",
    }
    assert expected.issubset(set(keys)), f"缺失: {expected - set(keys)}"


def test_load_registry_idempotent() -> None:
    """重复加载幂等。"""
    pm = PromptManager()
    pm.load_registry()
    pm.load_registry()
    assert len(pm.list_keys()) == 8


def test_load_registry_missing_file_returns_empty() -> None:
    """文件不存在 → 空 registry（不抛错）。"""
    pm = PromptManager(prompts_dir=Path("/nonexistent/path"))
    pm.load_registry()
    assert pm.list_keys() == []


# ============== 查询 ==============
def test_get_registry_entry_success() -> None:
    pm = PromptManager()
    pm.load_registry()
    entry = pm.get_registry_entry("authority_review")
    assert entry["prompt_key"] == "authority_review"
    assert entry["active_version"] == "v1.0.0"


def test_get_registry_entry_unknown_key_raises() -> None:
    pm = PromptManager()
    pm.load_registry()
    with pytest.raises(NotFoundError):
        pm.get_registry_entry("unknown_key")


def test_get_active_version_returns_v100() -> None:
    pm = PromptManager()
    pm.load_registry()
    assert pm.get_active_version("authority_review") == "v1.0.0"


def test_get_active_version_missing_config_raises() -> None:
    """registry 条目无 active_version → 抛 ValidationError。"""
    pm = PromptManager()
    pm.load_registry()
    pm._registry["bad_key"] = {"prompt_key": "bad_key"}  # type: ignore[assignment]
    with pytest.raises(ValidationError, match="active_version"):
        pm.get_active_version("bad_key")


# ============== PromptSpec 加载 ==============
def test_get_active_loads_prompt_spec() -> None:
    pm = PromptManager()
    pm.load_registry()
    spec = pm.get_active("authority_review")

    assert isinstance(spec, PromptSpec)
    assert spec.prompt_key == "authority_review"
    assert spec.version == "v1.0.0"
    assert spec.model_name == "qwen3.7-max"  # registry.yaml 统一管理，不再 YAML 硬编码
    assert spec.temperature == 0.2
    assert "issuing_authority" in spec.template
    # 模板含审查要点
    assert "法定制定主体清单" in spec.template


def test_get_active_cache_hit() -> None:
    """第二次调用从缓存返回（同一对象）。"""
    pm = PromptManager()
    pm.load_registry()
    spec1 = pm.get_active("authority_review")
    spec2 = pm.get_active("authority_review")
    assert spec1 is spec2


def test_get_active_yaml_file_missing_raises() -> None:
    """registry 声明了 active_version 但 YAML 文件不存在 → NotFoundError。"""
    pm = PromptManager()
    pm.load_registry()
    pm._registry["ghost"] = {  # type: ignore[assignment]
        "prompt_key": "ghost",
        "active_version": "v9.9.9",
    }
    with pytest.raises(NotFoundError):
        pm.get_active("ghost")


def test_list_versions_returns_all_local_files() -> None:
    pm = PromptManager()
    versions = pm.list_versions("authority_review")
    assert "v1.0.0" in versions


def test_list_versions_unknown_key_returns_empty() -> None:
    pm = PromptManager()
    assert pm.list_versions("unknown_key") == []


# ============== 渲染 ==============
def test_render_success() -> None:
    pm = PromptManager()
    pm.load_registry()
    rendered = pm.render(
        "authority_review",
        {
            "issuing_authority": "XX县人民政府",
            "doc_title": "XX县中小企业补贴办法",
            "legal_context": "《地方组织法》第七十六条...",
        },
    )
    assert "XX县人民政府" in rendered
    assert "XX县中小企业补贴办法" in rendered
    assert "《地方组织法》第七十六条..." in rendered


def test_render_missing_required_variable_raises() -> None:
    """缺失必填变量 → ValidationError。"""
    pm = PromptManager()
    pm.load_registry()
    with pytest.raises(ValidationError, match="缺失必填变量"):
        pm.render(
            "authority_review",
            {
                "doc_title": "测试",
                "legal_context": "...",
                # issuing_authority 缺失
            },
        )


def test_render_strict_undefined_unknown_var_raises() -> None:
    """Jinja2 StrictUndefined：模板引用未传入的变量 → ValidationError。"""
    pm = PromptManager()
    pm.load_registry()
    # doc_classify 的模板用到了 keywords，但 keywords 是 required=false，
    # 仍然会渲染（Jinja2 会用 Undefined → Strict 抛错）
    # 验证：传入 keywords 为 None 会失败，传入空列表则通过
    with pytest.raises(ValidationError):
        pm.render(
            "doc_classify",
            {
                "title": "测试",
                "issuing_authority": "测试机关",
                "body_text": "...",
                "keywords": None,
            },
        )


def test_render_with_list_variable() -> None:
    """list 类型变量正常渲染（join 过滤器）。"""
    pm = PromptManager()
    pm.load_registry()
    rendered = pm.render(
        "doc_classify",
        {
            "title": "测试文件",
            "issuing_authority": "测试机关",
            "body_text": "正文内容",
            "keywords": ["行政许可", "财政补贴"],
        },
    )
    assert "行政许可, 财政补贴" in rendered


# ============== 评估门控 ==============
@pytest.mark.asyncio
async def test_activate_rejects_low_eval_pass_rate() -> None:
    """评测通过率 < min_eval_pass_rate → 禁止激活（硬约束）。"""
    pm = PromptManager()
    pm.load_registry()

    # authority_review min_eval_pass_rate = 0.95
    session = AsyncMock()
    scalar_mock = MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    session.execute = AsyncMock(return_value=scalar_mock)

    with pytest.raises(ValidationError, match="禁止激活"):
        await pm.activate(session, "authority_review", "v1.0.0", 0.80)


@pytest.mark.asyncio
async def test_activate_success_deprecates_old_active() -> None:
    """激活新版本 → 旧 active 置为 deprecated + 新版本置为 active。"""
    pm = PromptManager()
    pm.load_registry()

    # mock 旧版本 + 新版本都存在
    old_prompt = MagicMock()
    old_prompt.status = PromptStatus.ACTIVE.value
    old_prompt.prompt_key = "authority_review"
    old_prompt.version = "v1.0.0"

    new_prompt = MagicMock()
    new_prompt.status = PromptStatus.DRAFT.value
    new_prompt.prompt_key = "authority_review"
    new_prompt.version = "v1.1.0"
    new_prompt.eval_pass_rate = None

    call_count = [0]

    async def _execute(stmt):
        call_count[0] += 1
        result = MagicMock()
        if call_count[0] == 1:
            # 第一次查询：旧 active
            result.scalar_one_or_none = MagicMock(return_value=old_prompt)
        else:
            # 第二次查询：新版本
            result.scalar_one_or_none = MagicMock(return_value=new_prompt)
        return result

    session = AsyncMock()
    session.execute = _execute
    session.flush = AsyncMock()

    activated = await pm.activate(
        session, "authority_review", "v1.1.0", 0.96
    )

    # 旧版本 deprecated
    assert old_prompt.status == PromptStatus.DEPRECATED.value
    # 新版本 active
    assert activated.status == PromptStatus.ACTIVE.value
    assert activated.eval_pass_rate == 0.96
    # registry active_version 更新
    assert pm.get_active_version("authority_review") == "v1.1.0"
    # 缓存清空
    assert "authority_review" not in pm._active_cache


@pytest.mark.asyncio
async def test_activate_unknown_version_raises_not_found() -> None:
    """激活未存在的版本 → NotFoundError。"""
    pm = PromptManager()
    pm.load_registry()

    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )
    # 旧 active 也不存在（让流程走到新版本查询）
    with pytest.raises(NotFoundError):
        await pm.activate(session, "authority_review", "v9.9.9", 0.99)


@pytest.mark.asyncio
async def test_deactivate_sets_deprecated() -> None:
    """回滚：版本置为 deprecated + 清缓存。"""
    pm = PromptManager()
    pm.load_registry()

    prompt = MagicMock()
    prompt.status = PromptStatus.ACTIVE.value
    prompt.prompt_key = "authority_review"
    prompt.version = "v1.0.0"

    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=prompt))
    )
    session.flush = AsyncMock()

    # 先放缓存
    pm._active_cache["authority_review"] = MagicMock(spec=PromptSpec)

    result = await pm.deactivate(session, "authority_review", "v1.0.0")
    assert result.status == PromptStatus.DEPRECATED.value
    assert "authority_review" not in pm._active_cache


# ============== sync_to_db ==============
@pytest.mark.asyncio
async def test_sync_to_db_inserts_missing_prompts() -> None:
    """DB 中不存在的 active 版本 → 从 YAML 加载并插入。"""
    pm = PromptManager()
    pm.load_registry()

    session = AsyncMock()
    # 模拟 DB 全部为空
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )
    session.flush = AsyncMock()

    added_objects: list = []

    def _add(obj):
        added_objects.append(obj)

    session.add = MagicMock(side_effect=_add)

    synced = await pm.sync_to_db(session)

    # 应插入 8 条（registry 中 8 个 prompt_key，每个插入 1 条）
    assert synced == 8
    assert len(added_objects) == 8
    # 验证插入对象
    first = added_objects[0]
    assert first.status == PromptStatus.ACTIVE.value
    assert first.version == "v1.0.0"
    assert first.template  # 非空


@pytest.mark.asyncio
async def test_sync_to_db_skips_existing_active() -> None:
    """已存在且 status=active 的版本 → 跳过。"""
    pm = PromptManager()
    pm.load_registry()

    existing_prompt = MagicMock()
    existing_prompt.status = PromptStatus.ACTIVE.value

    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=existing_prompt))
    )
    session.flush = AsyncMock()
    session.add = MagicMock()

    synced = await pm.sync_to_db(session)
    assert synced == 0
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_sync_to_db_reactivates_deprecated() -> None:
    """已存在但 status=deprecated 的版本 → 更新为 active。"""
    pm = PromptManager()
    pm.load_registry()

    # 每次 execute 返回一个新的 DEPRECATED prompt 对象（避免状态污染）
    def _make_deprecated_prompt():
        p = MagicMock()
        p.status = PromptStatus.DEPRECATED.value
        p.activated_at = None
        return p

    execute_call_count = [0]

    async def _execute(stmt):
        execute_call_count[0] += 1
        return MagicMock(scalar_one_or_none=MagicMock(return_value=_make_deprecated_prompt()))

    session = AsyncMock()
    session.execute = _execute
    session.flush = AsyncMock()
    session.add = MagicMock()

    synced = await pm.sync_to_db(session)
    assert synced == 8
    session.add.assert_not_called()


# ============== 单例 ==============
def test_get_prompt_manager_singleton() -> None:
    pm1 = get_prompt_manager()
    pm2 = get_prompt_manager()
    assert pm1 is pm2


def test_prompt_dir_exists() -> None:
    """PROMPTS_DIR 指向存在的 prompts 目录。"""
    assert PROMPTS_DIR.exists()
    assert (PROMPTS_DIR / "registry.yaml").exists()
    assert (PROMPTS_DIR / "authority_review" / "v1.0.0.yaml").exists()


# ============== invalidate_cache ==============
def test_invalidate_cache_single_key() -> None:
    pm = PromptManager()
    pm.load_registry()
    pm.get_active("authority_review")
    assert "authority_review" in pm._active_cache

    pm.invalidate_cache("authority_review")
    assert "authority_review" not in pm._active_cache


def test_invalidate_cache_all() -> None:
    pm = PromptManager()
    pm.load_registry()
    pm.get_active("authority_review")
    pm.get_active("doc_classify")
    assert len(pm._active_cache) == 2

    pm.invalidate_cache()
    assert len(pm._active_cache) == 0
