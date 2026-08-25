"""Redis 客户端封装 (单例) - 异步连接。"""
from __future__ import annotations

import redis.asyncio as aioredis

from app.core.config import get_settings

_client: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    """获取全局 Redis 异步客户端（懒加载单例）。"""
    global _client
    if _client is None:
        settings = get_settings()
        _client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _client


async def close_redis() -> None:
    """关闭 Redis 客户端（应用关闭时调用）。"""
    global _client
    if _client is not None:
        try:
            await _client.aclose()
        except Exception:  # noqa: BLE001
            pass
        _client = None


async def is_redis_alive() -> bool:
    """快速 ping, 失败用于限流降级。"""
    try:
        client = get_redis()
        return bool(await client.ping())
    except Exception:  # noqa: BLE001
        return False
