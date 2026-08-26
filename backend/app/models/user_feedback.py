"""用户反馈中心模型 T25 - 用户对 AI 输出表达态度/意见。

与 feedback_cases (T09) 的区别：
- feedback_cases: 审稿人对 AI 风险的「修改前后对比」+ 修改原因（FR-032，面向 prompt 优化）
- user_feedback: 用户对 AI 输出的一般性反馈（👍/👎 + 可选文字 + 状态流转，面向产品改进）

两者不混淆：不同的表、不同的端点、不同的审计用途。
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPkMixin


class UserFeedback(UUIDPkMixin, TimestampMixin, Base):
    """用户反馈表 T25。

    字段：
    - user_id:        提交反馈的用户
    - target_kind:    目标类型（report / review / risk / assistant）
    - target_id:      目标 id 字符串（与 FeedbackBar 的 targetId 一致）
    - target_label:   冗余人类可读标签，便于列表/详情直接渲染
    - vote:           up / down / neutral
    - comment:        用户补充文字（可空，≤2000 字符）
    - status:         open / triaged / resolved / wontfix
    - admin_reply:    管理员回复（可空，≤1000 字符）
    - context:        JSONB 上下文（节点名/风险id等，便于溯源）
    - closed_at:      用户主动关闭/已读时间
    """

    __tablename__ = "user_feedback"

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # M16.1: 多租户隔离列 — 通过 user_id → users 回填
    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str] = mapped_column(String(64), nullable=False)
    target_label: Mapped[str] = mapped_column(String(256), nullable=False)
    vote: Mapped[str] = mapped_column(String(8), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="open"
    )
    admin_reply: Mapped[str | None] = mapped_column(Text, nullable=True)
    context: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


__all__ = ["UserFeedback"]
