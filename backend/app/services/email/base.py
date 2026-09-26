"""Email Provider 抽象基类 + 数据结构。

实现:
- base.py   Protocol + EmailResult
- mock.py   MockEmailProvider (开发 + 测试)
- smtp.py   SmtpEmailProvider (真实 SMTP, smtplib 标准库)
- factory.py get_email_provider() 根据 EMAIL_PROVIDER env 切换
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class EmailResult:
    """邮件发送结果。"""

    success: bool
    provider: str
    message_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    mock_code: str | None = None  # Mock 模式下携带验证码, 便于开发联调


class EmailProvider(Protocol):
    """Email Provider 协议。

    实现要求:
    - send_code 必须返回 EmailResult
    - 失败时不抛异常, 通过 success=False 表达
    - 不打日志包含明文验证码 (用 mock_code 字段传递)
    """

    name: str

    async def send_code(
        self,
        *,
        email: str,
        code: str,
        purpose: str,
        ttl_seconds: int,
    ) -> EmailResult: ...