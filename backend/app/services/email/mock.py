"""Mock Email Provider - 仅用于开发、测试。

行为:
- 永远 success
- 把验证码写日志 (level=DEBUG), 不真正发邮件
- 仅在非生产环境通过 mock_code 字段返回验证码
"""
from __future__ import annotations

import uuid

import structlog

from app.services.email.base import EmailProvider, EmailResult

_log = structlog.get_logger("auth.email.mock")


class MockEmailProvider(EmailProvider):
    """本地开发 / 测试用 Email Provider。"""

    name = "mock"

    def __init__(self, *, expose_code: bool = False) -> None:
        self._expose_code = expose_code

    async def send_code(
        self,
        *,
        email: str,
        code: str,
        purpose: str,
        ttl_seconds: int,
    ) -> EmailResult:
        message_id = f"mock-{uuid.uuid4().hex[:12]}"
        _log.debug(
            "mock_email_code_for_debug",
            email=email,
            purpose=purpose,
            code=code,
        )
        return EmailResult(
            success=True,
            provider=self.name,
            message_id=message_id,
            mock_code=code if self._expose_code else None,
        )