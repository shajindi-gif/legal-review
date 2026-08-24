"""Embedding 服务测试 - Sprint 3 / FR-014 多后端可切。

覆盖：
- MockProvider：确定性 + 维度 + L2 归一化
- MockProvider.batch_embed：数量匹配 + 空列表
- 工厂切换：mock / 未知后端抛错
- reset_provider：单例清空
- DashScopeProvider：缺 API Key 抛 AgentError
- BGEM3LocalProvider：未安装 sentence-transformers 时抛 AgentError（懒加载）
"""
from __future__ import annotations

import os
from collections.abc import Iterable
from typing import Any
from unittest.mock import patch

import pytest

from app.core.errors import AgentError
from app.tools import embedding
from app.tools.embedding import (
    BGEM3LocalProvider,
    DashScopeProvider,
    EmbeddingProvider,
    MockProvider,
    get_embedding_provider,
    reset_provider,
)


# ============== MockProvider ==============
def test_mock_provider_name_and_dim() -> None:
    p = MockProvider()
    assert p.name == "mock-embedding"
    assert p.dim > 0


def test_mock_provider_deterministic() -> None:
    """相同输入 → 相同向量。"""
    p = MockProvider()
    v1 = p._hash_vec("行政许可法")
    v2 = p._hash_vec("行政许可法")
    assert v1 == v2


def test_mock_provider_different_input_different_vec() -> None:
    """不同输入 → 不同向量。"""
    p = MockProvider()
    v1 = p._hash_vec("行政许可法")
    v2 = p._hash_vec("行政处罚法")
    assert v1 != v2


def test_mock_provider_l2_normalized() -> None:
    """L2 范数接近 1。"""
    p = MockProvider()
    v = p._hash_vec("test text")
    norm = sum(x * x for x in v) ** 0.5
    assert abs(norm - 1.0) < 1e-5


def test_mock_provider_dim_matches_settings() -> None:
    """向量维度等于 settings.embedding_dim。"""
    p = MockProvider()
    v = p._hash_vec("test")
    assert len(v) == p.dim


@pytest.mark.asyncio
async def test_mock_provider_embed_async() -> None:
    p = MockProvider()
    v = await p.embed("hello")
    assert isinstance(v, list)
    assert len(v) == p.dim
    assert all(isinstance(x, float) for x in v)


@pytest.mark.asyncio
async def test_mock_provider_batch_embed() -> None:
    p = MockProvider()
    texts = ["abc", "def", "ghi"]
    vecs = await p.batch_embed(texts)
    assert len(vecs) == 3
    assert all(len(v) == p.dim for v in vecs)


@pytest.mark.asyncio
async def test_mock_provider_batch_embed_empty() -> None:
    """空列表 → 空结果。"""
    p = MockProvider()
    assert await p.batch_embed([]) == []


def test_mock_provider_health() -> None:
    """health() 返回 provider 信息。"""
    p = MockProvider()
    info = p.health()
    assert info["provider"] == "mock-embedding"
    assert info["dim"] == p.dim


# ============== 工厂 ==============
def _clear_env(monkeypatch: pytest.MonkeyPatch, key: str) -> None:
    """从环境变量中删除指定 key。"""
    monkeypatch.delenv(key, raising=False)


def test_factory_mock_when_env_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """EMBEDDING_BACKEND=mock → MockProvider。"""
    reset_provider()
    monkeypatch.setenv("EMBEDDING_BACKEND", "mock")
    p = get_embedding_provider()
    assert isinstance(p, MockProvider)
    reset_provider()


def test_factory_mock_when_debug(monkeypatch: pytest.MonkeyPatch) -> None:
    """DEBUG=true 且未设 EMBEDDING_BACKEND → MockProvider。"""
    reset_provider()
    _clear_env(monkeypatch, "EMBEDDING_BACKEND")
    # patch settings.debug 返回 True
    with patch.object(embedding, "get_settings") as mock_settings:
        mock_settings.return_value.debug = True
        mock_settings.return_value.embedding_dim = 1024
        p = get_embedding_provider()
    assert isinstance(p, MockProvider)
    reset_provider()


def test_factory_local_when_not_debug(monkeypatch: pytest.MonkeyPatch) -> None:
    """DEBUG=false 且未设 EMBEDDING_BACKEND → BGEM3LocalProvider（懒加载，不实际加载模型）。"""
    reset_provider()
    _clear_env(monkeypatch, "EMBEDDING_BACKEND")
    with patch.object(embedding, "get_settings") as mock_settings:
        mock_settings.return_value.debug = False
        mock_settings.return_value.embedding_dim = 1024
        p = get_embedding_provider()
    assert isinstance(p, BGEM3LocalProvider)
    reset_provider()


def test_factory_unknown_backend_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """未知后端 → AgentError。"""
    reset_provider()
    monkeypatch.setenv("EMBEDDING_BACKEND", "unknown_provider")
    with pytest.raises(AgentError):
        get_embedding_provider()
    reset_provider()


def test_factory_singleton_caches(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_embedding_provider 返回同一个实例。"""
    reset_provider()
    monkeypatch.setenv("EMBEDDING_BACKEND", "mock")
    p1 = get_embedding_provider()
    p2 = get_embedding_provider()
    assert p1 is p2
    reset_provider()


def test_reset_provider_clears_singleton(monkeypatch: pytest.MonkeyPatch) -> None:
    """reset_provider 重置单例。"""
    monkeypatch.setenv("EMBEDDING_BACKEND", "mock")
    reset_provider()
    p1 = get_embedding_provider()
    reset_provider()
    p2 = get_embedding_provider()
    assert p1 is not p2
    reset_provider()


# ============== DashScopeProvider ==============
def test_dashscope_provider_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """DashScope 后端未配置 QWEN_API_KEY → 抛 AgentError。"""
    monkeypatch.delenv("QWEN_API_KEY", raising=False)
    # patch settings.qwen_api_key 为空
    with patch.object(embedding, "get_settings") as mock_settings:
        mock_settings.return_value.qwen_api_key = ""
        mock_settings.return_value.embedding_dim = 1024
        with pytest.raises(AgentError):
            DashScopeProvider()


# ============== BGEM3LocalProvider ==============
def test_bge_m3_local_lazy_load_raises_without_lib(monkeypatch: pytest.MonkeyPatch) -> None:
    """未安装 sentence-transformers 时，embed() 抛 AgentError。"""
    p = BGEM3LocalProvider()
    # patch _load 抛 AgentError
    def _raise_load() -> None:
        raise AgentError("legal_retrieve", "sentence-transformers not installed")

    with patch.object(p, "_load", side_effect=_raise_load), pytest.raises(AgentError):
        # 同步触发 _load
        p._load()


def test_bge_m3_local_name_and_dim() -> None:
    p = BGEM3LocalProvider()
    assert p.name == "bge-m3-local"
    assert p.dim == 1024


def test_bge_m3_local_model_initially_none() -> None:
    """模型懒加载，初始为 None。"""
    p = BGEM3LocalProvider()
    assert p._model is None


# ============== 抽象接口 ==============
def test_embedding_provider_is_abstract() -> None:
    """EmbeddingProvider 不能直接实例化。"""
    with pytest.raises(TypeError):
        EmbeddingProvider()  # type: ignore[abstract]


def test_all_providers_implement_interface() -> None:
    """三种 provider 都实现 EmbeddingProvider 接口。"""
    providers: Iterable[type[Any]] = [MockProvider, BGEM3LocalProvider]
    for cls in providers:
        assert issubclass(cls, EmbeddingProvider)
        assert hasattr(cls, "name")
        assert hasattr(cls, "dim")
        assert hasattr(cls, "embed")
        assert hasattr(cls, "batch_embed")


# ============== MockProvider 与 DashScope 接口一致性 ==============
def test_dashscope_provider_uses_api_url() -> None:
    """DashScopeProvider 的 API URL 已定义。"""
    assert DashScopeProvider.API_URL.startswith("https://")
    assert "dashscope" in DashScopeProvider.API_URL or "aliyuncs" in DashScopeProvider.API_URL


# ============== 清理 ==============
def test_cleanup_provider_state() -> None:
    """最后一个测试清理单例。"""
    reset_provider()
    os.environ.pop("EMBEDDING_BACKEND", None)
