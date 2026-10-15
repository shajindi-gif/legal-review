"""用户行为埋点模型 —— 商业化最小集。

记录匿名/登录用户的关键转化事件（page_view → signup → order_paid），
用于漏斗分析与付费转化归因。所有写入路径均为 best-effort，绝不阻断主流程。
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AnalyticsEvent(Base):
    """埋点事件表 analytics_events。

    字段：
    - user_id:      登录用户 UUID（服务端从 JWT 解析，绝不采信请求体传入）；匿名事件为 NULL
    - anonymous_id: 前端持久化的匿名 ID（localStorage，UUID 字符串，非 PII）
    - session_id:   前端会话 ID（可选）
    - event:        事件名（服务端白名单 12 个之一）
    - properties:   JSONB 事件属性（plan_tier / channel 等，禁止 PII）
    - page/referrer/ua/ip_hash: 页面与客户端上下文（ip 为哈希，不存原文）
    """

    __tablename__ = "analytics_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    anonymous_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event: Mapped[str] = mapped_column(String(64), nullable=False)
    properties: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    page: Mapped[str | None] = mapped_column(String(128), nullable=True)
    referrer: Mapped[str | None] = mapped_column(String(256), nullable=True)
    ua: Mapped[str | None] = mapped_column(String(256), nullable=True)
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)


__all__ = ["AnalyticsEvent"]
