"""轻量级 Rate Limit 服务 (M0)。

实现:
- 优先使用 Redis (固定窗口 + INCR + EXPIRE)
- Redis 不可用时降级为内存 in-process counter
- 业务方调用 `check_and_incr(scope, key, limit, window_seconds)`,
  超限抛 RateLimitedError。

使用约定:
- scope 是动作标识, e.g. "sms_send:phone" / "register:ip"
- key 是限流维度值, e.g. 手机号 / IP
- limit + window_seconds 是窗口内允许的最大次数
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Deque

import structlog

from app.core.errors import RateLimitedError
from app.core.redis import get_redis, is_redis_alive

_log = structlog.get_logger("auth.rate_limit")

# ============== 内存降级 (Redis 不可用时使用, 仅限单进程; 多 uvicorn worker 各自计数) ==============
_inmem_buckets: dict[str, Deque[float]] = defaultdict(deque)


def _inmem_check_and_incr(scope: str, key: str, limit: int, window_seconds: int) -> None:
    bucket_key = f"{scope}:{key}"
    now = time.monotonic()
    cutoff = now - window_seconds
    q = _inmem_buckets[bucket_key]
    while q and q[0] < cutoff:
        q.popleft()
    if len(q) >= limit:
        raise RateLimitedError()
    q.append(now)


async def _redis_check_and_incr(scope: str, key: str, limit: int, window_seconds: int) -> None:
    client = get_redis()
    redis_key = f"rl:{scope}:{key}"
    pipe = client.pipeline()
    pipe.incr(redis_key)
    pipe.expire(redis_key, window_seconds)
    count, _exp = await pipe.execute()
    if int(count) > limit:
        raise RateLimitedError()


async def check_and_incr(
    scope: str,
    key: str,
    limit: int,
    window_seconds: int,
) -> None:
    """检查 + 自增 一次请求; 超限抛 RateLimitedError。

    Args:
        scope: 动作维度, e.g. "sms_send_phone"
        key: 限流维度值 (手机号 / IP)
        limit: 窗口内允许最大次数
        window_seconds: 窗口长度 (秒)

    Raises:
        RateLimitedError: 超过 limit
    """
    if not key:
        return  # 缺失维度不阻塞业务
    try:
        if await is_redis_alive():
            await _redis_check_and_incr(scope, key, limit, window_seconds)
            return
    except RateLimitedError:
        raise
    except Exception as e:  # noqa: BLE001
        _log.warning("rate_limit_redis_failed_fallback_inmem", error=str(e))

    # 降级到进程内内存
    _inmem_check_and_incr(scope, key, limit, window_seconds)
