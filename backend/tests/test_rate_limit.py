"""RateLimit 单元测试 - Redis 不可用时降级到内存, 基本窗口语义正确。"""
from __future__ import annotations

import pytest

from app.core.errors import RateLimitedError
from app.services.rate_limit import (
    _inmem_buckets,
    _inmem_check_and_incr,
    check_and_incr,
)


@pytest.fixture(autouse=True)
def _reset_inmem():
    _inmem_buckets.clear()
    yield
    _inmem_buckets.clear()


# ============== 内存实现 ==============


def test_inmem_under_limit_passes() -> None:
    for _ in range(3):
        _inmem_check_and_incr("scope", "key", limit=3, window_seconds=60)


def test_inmem_over_limit_raises() -> None:
    _inmem_check_and_incr("scope", "key", limit=2, window_seconds=60)
    _inmem_check_and_incr("scope", "key", limit=2, window_seconds=60)
    with pytest.raises(RateLimitedError):
        _inmem_check_and_incr("scope", "key", limit=2, window_seconds=60)


def test_inmem_different_keys_independent() -> None:
    _inmem_check_and_incr("scope", "key-a", limit=1, window_seconds=60)
    with pytest.raises(RateLimitedError):
        _inmem_check_and_incr("scope", "key-a", limit=1, window_seconds=60)
    # key-b 不受影响
    _inmem_check_and_incr("scope", "key-b", limit=1, window_seconds=60)


def test_inmem_empty_key_does_not_block() -> None:
    # 没有 key 跳过 (业务容错)
    _inmem_check_and_incr("scope", "", limit=1, window_seconds=60)


# ============== 异步 check_and_incr (Redis 不可用 → 走内存) ==============


@pytest.mark.asyncio
async def test_check_and_incr_falls_back_to_memory_when_redis_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """让 is_redis_alive() 永远返回 False, 验证降级到内存路径。"""

    async def _fake_alive() -> bool:
        return False

    monkeypatch.setattr("app.services.rate_limit.is_redis_alive", _fake_alive)

    # 3 次都过
    for _ in range(3):
        await check_and_incr("test_scope", "test_key", limit=3, window_seconds=60)
    # 第 4 次 raise
    with pytest.raises(RateLimitedError):
        await check_and_incr("test_scope", "test_key", limit=3, window_seconds=60)
