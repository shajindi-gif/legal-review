"""通知中心 ORM 模型（UI-M8）。

一张 T24 notifications 表，覆盖审查节点进度（running/done）。
- 触发源：agent 节点钩子（security_checked 装饰器扩展）
- 读取：/api/v1/notifications 列表 + 未读数
- 写入：/api/v1/notifications/{id}/read 标记 / /read-all 全部标记

设计要点：
- recipient_id 索引：每个用户独立 inbox
- read_at：NULL 即未读；分页/计数都不需要 status 字段
- payload JSONB：节点级别 payload（node_name、iteration 等），不破坏可扩展性
- link 字段：直接给出"跳到哪"的 URL 前缀，前端拼接 task_id
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Notification(Base):
    """UI-M8 通知表 T24。

    字段语义：
    - kind：通知类型，当前只有 "node_progress"，未来可扩 risk_found / review_done
    - title / body：铃铛下拉与列表页直接渲染的文本
    - task_id：可选；非审查类通知时为 NULL
    - link：可选跳转目标，相对路径如 /review/{task_id}
    - read_at：NULL 即未读
    - payload：JSONB 兜底（节点名/iteration/severity 等）
    """

    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notif_recipient_unread", "recipient_id", "read_at", "created_at"),
        Index("ix_notif_recipient_created", "recipient_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("uuid_generate_v4()"),
    )
    recipient_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    # M16.1: 多租户隔离列 — 通过 recipient_id → users 回填
    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="node_progress")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    task_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("review_tasks.id", ondelete="SET NULL"),
        nullable=True,
    )
    link: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        flag = "unread" if self.read_at is None else "read"
        return f"<Notification {self.kind} {self.recipient_id} [{flag}]>"
