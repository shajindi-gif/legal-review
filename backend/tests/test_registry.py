"""Tool Registry 测试 - Sprint 4 / 硬约束#3 未注册工具禁止调用。

覆盖：
- list_tools 返回全部已注册工具
- get_tool 已注册工具返回可调用对象
- get_tool 未注册工具抛 ValidationError
- get_tool 版本不匹配抛 ValidationError
- get_tool 正确版本通过
- ToolSpec 不可变（frozen）
"""
from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from app.core.errors import ValidationError
from app.tools.registry import TOOL_REGISTRY, ToolSpec, get_tool, list_tools


# ============== list_tools ==============
def test_list_tools_returns_all_registered() -> None:
    """list_tools 返回全部已注册工具。"""
    tools = list_tools()
    assert len(tools) == len(TOOL_REGISTRY)
    names = {t.name for t in tools}
    # 核心工具均在册
    for required in (
        "rag_search", "llm_complete", "structure_extractor",
        "docx_parser", "pdf_parser", "txt_parser",
    ):
        assert required in names, f"缺失工具: {required}"


def test_list_tools_entries_are_tool_spec() -> None:
    """每条注册项均为 ToolSpec 实例。"""
    for spec in list_tools():
        assert isinstance(spec, ToolSpec)
        assert spec.version  # 版本号非空


# ============== get_tool 已注册 ==============
def test_get_tool_structure_extractor_returns_callable() -> None:
    """structure_extractor 返回可调用的 parse 入口。"""
    fn = get_tool("structure_extractor")
    assert callable(fn)


def test_get_tool_rag_search_returns_class() -> None:
    """rag_search 返回 RAGSearchService 类。"""
    cls = get_tool("rag_search")
    assert hasattr(cls, "search_simple")


def test_get_tool_llm_complete_returns_provider_factory() -> None:
    """llm_complete 返回 get_llm_provider 工厂函数。"""
    fn = get_tool("llm_complete")
    assert callable(fn)


def test_get_tool_prompt_manager_returns_manager_factory() -> None:
    """prompt_manager 返回 get_prompt_manager 工厂函数。"""
    fn = get_tool("prompt_manager")
    assert callable(fn)


# ============== get_tool 未注册 ==============
def test_get_tool_unregistered_raises() -> None:
    """未注册工具抛 ValidationError（硬约束：未注册工具禁止调用）。"""
    with pytest.raises(ValidationError, match="unregistered tool"):
        get_tool("nonexistent_tool")


def test_get_tool_empty_name_raises() -> None:
    """空字符串工具名抛 ValidationError。"""
    with pytest.raises(ValidationError, match="unregistered tool"):
        get_tool("")


# ============== get_tool 版本校验 ==============
def test_get_tool_version_mismatch_raises() -> None:
    """请求版本与注册版本不匹配抛 ValidationError。"""
    with pytest.raises(ValidationError, match="version mismatch"):
        get_tool("rag_search", version="v9.9.9")


def test_get_tool_correct_version_passes() -> None:
    """请求正确版本正常返回。"""
    registered = TOOL_REGISTRY["structure_extractor"].version
    fn = get_tool("structure_extractor", version=registered)
    assert callable(fn)


# ============== ToolSpec 不可变 ==============
def test_tool_spec_is_frozen() -> None:
    """ToolSpec 为 frozen dataclass，不可修改。"""
    spec = TOOL_REGISTRY["rag_search"]
    with pytest.raises(FrozenInstanceError):
        spec.name = "tampered"  # type: ignore[misc]
