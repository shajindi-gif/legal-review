"""Embedding 服务 - 多后端可切（local / api / mock）。

设计：
1. EmbeddingProvider 抽象接口
2. 三种实现：
   - BGEM3LocalProvider：本地 sentence-transformers（懒加载，避免启动慢）
   - DashScopeProvider：调 DashScope text-embedding-v3 API
   - MockProvider：测试用，确定性 hash → 向量
3. EmbeddingService 工厂：根据 settings 选择后端
4. 统一接口：embed(text) / batch_embed(texts)

硬约束：
- 维度由 settings.embedding_dim 决定（默认 1024，BGE-M3）
- 失败时抛 AgentError，不静默返回零向量（除 MockProvider）
- 全部 LLM/Embedding 调用走内部 Gateway，禁止直连第三方（Security Harness）
"""

from __future__ import annotations

import hashlib
import os
from abc import ABC, abstractmethod
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.errors import AgentError
from app.core.logging import get_logger

logger = get_logger("tools.embedding")


# ============== 抽象接口 ==============
class EmbeddingProvider(ABC):
    """Embedding 后端抽象。"""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def dim(self) -> int: ...

    @abstractmethod
    async def embed(self, text: str) -> list[float]: ...

    @abstractmethod
    async def batch_embed(self, texts: list[str]) -> list[list[float]]: ...


    def health(self) -> dict[str, Any]:
        return {"provider": self.name, "dim": self.dim}


# ============== 1. 本地 BGE-M3 ==============
class BGEM3LocalProvider(EmbeddingProvider):
    """本地 BGE-M3（sentence-transformers，懒加载）。

    安装：pip install sentence-transformers
    模型首次会从 HuggingFace 下载（约 2GB），缓存到 ~/.cache/huggingface
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._model = None  # 懒加载

    @property
    def name(self) -> str:
        return "bge-m3-local"

    @property
    def dim(self) -> int:
        return self._settings.embedding_dim

    def _load(self) -> None:
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as e:
                raise AgentError(
                    "legal_retrieve",
                    f"sentence-transformers not installed: {e}. "
                    "安装：pip install sentence-transformers",
                ) from e
            logger.info("bge_m3_loading", model="BAAI/bge-m3")
            self._model = SentenceTransformer(
                model_name_or_path="BAAI/bge-m3",
                device="cpu",  # 服务端 CPU 推理，避免 GPU 依赖
            )

    async def embed(self, text: str) -> list[float]:
        self._load()
        # SentenceTransformer 是同步接口，包到 async 调用
        vec = self._model.encode(text, normalize_embeddings=True)
        return vec.tolist()

    async def batch_embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        self._load()
        vecs = self._model.encode(texts, normalize_embeddings=True, batch_size=32)
        return [v.tolist() for v in vecs]


# ============== 2. DashScope API ==============
class DashScopeProvider(EmbeddingProvider):
    """DashScope text-embedding-v3 API（阿里云，OpenAI 兼容模式）。

    优势：无需本地模型，按量计费；与 Qwen 同账号体系。
    劣势：法规原文上传第三方，需评估合规（默认关闭，由 .env 显式启用）。

    端点：{qwen_base_url}/embeddings（compatible-mode，OpenAI 兼容格式）
    模型：text-embedding-v3（1024 维，与 EMBEDDING_DIM 匹配）
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        if not self._settings.qwen_api_key:
            raise AgentError("legal_retrieve", "DashScope 需配置 QWEN_API_KEY")

    @property
    def name(self) -> str:
        return "dashscope-embedding"

    @property
    def dim(self) -> int:
        return self._settings.embedding_dim

    async def embed(self, text: str) -> list[float]:
        result = await self.batch_embed([text])
        return result[0]

    async def batch_embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        url = f"{self._settings.qwen_base_url}/embeddings"
        # 分批处理（DashScope 单次上限 25 条，保守取 10）
        all_vecs: list[list[float]] = []
        batch_size = 10
        async with httpx.AsyncClient(timeout=30) as client:
            for i in range(0, len(texts), batch_size):
                batch = texts[i : i + batch_size]
                resp = await client.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {self._settings.qwen_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "text-embedding-v3",
                        "input": batch,
                        "dimensions": self._settings.embedding_dim,
                        "encoding_format": "float",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                if data.get("code") or data.get("error"):
                    msg = data.get("message") or data.get("error", {}).get("message")
                    raise AgentError(
                        "legal_retrieve",
                        f"DashScope embedding error: {msg}",
                    )
                # OpenAI 兼容格式：data[i].embedding
                all_vecs.extend([item["embedding"] for item in data["data"]])
        return all_vecs


# ============== 3. Mock（测试用） ==============
class MockProvider(EmbeddingProvider):
    """Mock Embedding - 确定性 hash → 向量。

    测试 / CI 用：相同输入总是返回相同向量（不依赖任何模型）。
    语义无关，但能跑通 RAG 全链路验证。
    """

    def __init__(self) -> None:
        self._settings = get_settings()

    @property
    def name(self) -> str:
        return "mock-embedding"

    @property
    def dim(self) -> int:
        return self._settings.embedding_dim

    def _hash_vec(self, text: str) -> list[float]:
        """确定性 hash → 归一化向量。

        注意：SHA-256 字节流解为 IEEE-754 float32 时，约 0.4% 的位置会
        落到 NaN / ±Inf 区段（指数全 1）。归一化前必须先把这些位置清零，
        否则 norm = sqrt(sum(x*x)) 会因为单个 NaN 传播到整个向量，
        导致 x/norm 全部变成 NaN。
        """
        h = hashlib.sha256(text.encode("utf-8")).digest()
        # 复制 hash 到 dim 长度
        needed = self._settings.embedding_dim
        bytes_needed = needed * 4  # float32 = 4 bytes
        buf = bytearray()
        counter = 0
        while len(buf) < bytes_needed:
            buf.extend(hashlib.sha256(h + counter.to_bytes(4, "big")).digest())
            counter += 1
        import struct

        raw = list(struct.unpack(f">{needed}f", bytes(buf[:bytes_needed])))
        # 过滤 NaN / ±Inf（IEEE-754 随机字节会偶尔产生），归零避免污染 norm
        inf = (float("inf"), float("-inf"))
        floats = [0.0 if (x != x or x in inf) else x for x in raw]
        # L2 归一化
        norm = sum(x * x for x in floats) ** 0.5
        if norm == 0:
            return [0.0] * needed
        return [x / norm for x in floats]

    async def embed(self, text: str) -> list[float]:
        return self._hash_vec(text)

    async def batch_embed(self, texts: list[str]) -> list[list[float]]:
        return [self._hash_vec(t) for t in texts]


# ============== 工厂 ==============
_provider: EmbeddingProvider | None = None


def get_embedding_provider() -> EmbeddingProvider:
    """单例工厂 - 根据 settings 选择后端。

    选择优先级：
    1. settings.embedding_backend 显式指定（local/api/mock）
    2. DEBUG=true 时默认 mock（避免开发环境拉模型）
    3. 否则 local
    """
    global _provider
    if _provider is not None:
        return _provider

    settings = get_settings()
    backend = (settings.embedding_backend or "").lower()
    if not backend:
        backend = "mock" if settings.debug else "local"

    if backend == "mock":
        _provider = MockProvider()
    elif backend == "api":
        _provider = DashScopeProvider()
    elif backend == "local":
        _provider = BGEM3LocalProvider()
    else:
        raise AgentError("legal_retrieve", f"unknown EMBEDDING_BACKEND: {backend}")

    logger.info("embedding_provider_initialized", backend=_provider.name, dim=_provider.dim)
    return _provider


def reset_provider() -> None:
    """测试用：重置单例。"""
    global _provider
    _provider = None
