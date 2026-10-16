"""用户行为埋点 API：POST /api/v1/analytics/events（单条或批量 ≤50，白名单校验）。

设计要点：
- 鉴权可选：user_id 只从 Authorization Bearer JWT 解析，解析失败为 None；
  绝不采信请求体传入的任何身份字段。
- 逐条 try/except 入库，任何失败都不影响其他事件与响应。
- 无 PII：只落匿名 ID / 页面 / UA / IP 哈希。
"""

from __future__ import annotations

import hashlib
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import decode_token, get_db
from app.core.logging import get_logger
from app.models.analytics import AnalyticsEvent

logger = get_logger("analytics")

router = APIRouter(prefix="/analytics", tags=["analytics"])

# 事件白名单（与 frontend/src/lib/analytics.ts 保持一致）
EVENT_WHITELIST: frozenset[str] = frozenset(
    {
        "page_view",
        "pricing_view",
        "signup_submit",
        "first_task_started",
        "task_completed",
        "quota_exhausted",
        "upgrade_dialog_view",
        "upgrade_click",
        "order_created",
        "order_paid",
        "landing_view",
        "custom_error",
        # ---- 认证转化漏斗（P0 升级）----
        "auth_page_view",
        "signup_start",
        "signup_success",
        "login_success",
        "login_failed",
        "verification_sent",
        "verification_success",
        "verification_failed",
        "password_reset_success",
        "onboarding_completed",
    }
)

MAX_BATCH = 50


class AnalyticsEventIn(BaseModel):
    """单条埋点事件入参（无任何身份字段，user_id 由服务端解析）。"""

    event: str = Field(..., max_length=64)
    properties: dict = Field(default_factory=dict)
    page: str | None = Field(default=None, max_length=128)
    referrer: str | None = Field(default=None, max_length=256)
    anonymous_id: str | None = Field(default=None, max_length=64)
    session_id: str | None = Field(default=None, max_length=64)

    @field_validator("event")
    @classmethod
    def _check_whitelist(cls, v: str) -> str:
        if v not in EVENT_WHITELIST:
            raise ValueError(f"未支持的事件类型: {v}")
        return v


class AnalyticsBatchIn(BaseModel):
    """批量埋点入参，单次最多 50 条。"""

    events: list[AnalyticsEventIn] = Field(..., max_length=MAX_BATCH)


def _parse_user_id(authorization: str | None) -> UUID | None:
    """从 Bearer JWT 解析 user_id；任何解析失败一律返回 None。"""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = decode_token(token)
        return UUID(str(payload.get("sub")))
    except Exception:
        # 过期/无效/非本地 token（如 Core token）→ 视为匿名
        return None


def _ip_hash(request: Request) -> str | None:
    """客户端 IP 哈希（sha256 截断 64 字符），不落 IP 原文。"""
    client_ip = request.client.host if request.client else None
    if not client_ip:
        return None
    return hashlib.sha256(client_ip.encode("utf-8")).hexdigest()[:64]


@router.post("/events")
async def post_events(
    payload: AnalyticsEventIn | AnalyticsBatchIn,
    request: Request,
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """接收单条或批量埋点事件，返回实际入库条数。"""
    user_id = _parse_user_id(authorization)
    ua = (request.headers.get("user-agent") or "")[:256] or None
    ip_hash = _ip_hash(request)

    items = [payload] if isinstance(payload, AnalyticsEventIn) else payload.events

    accepted = 0
    for item in items:
        try:
            session.add(
                AnalyticsEvent(
                    user_id=user_id,
                    anonymous_id=item.anonymous_id,
                    session_id=item.session_id,
                    event=item.event,
                    properties=item.properties,
                    page=item.page,
                    referrer=item.referrer,
                    ua=ua,
                    ip_hash=ip_hash,
                )
            )
            accepted += 1
        except Exception as e:
            # 单条失败只跳过该条，绝不影响其余事件
            logger.warning("analytics_event_add_failed", event_name=item.event, error=str(e))

    try:
        await session.commit()
    except Exception as e:
        logger.warning("analytics_commit_failed", count=accepted, error=str(e))
        return {"accepted": 0}

    return {"accepted": accepted}
