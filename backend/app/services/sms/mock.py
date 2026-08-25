"""Mock SMS Provider - 仅用于开发、测试、M0 阶段。

行为:
- 永远 success
- 把验证码写日志 (level=INFO), 不写到手机
- 在响应里通过 mock_code 字段返回验证码, 仅在 SMS_PROVIDER=mock 时生效

生产环境: 必须切到 tencent / aliyun; 否则该 provider 在 SMS_PROVIDER=production
时直接抛错 (factory 层校验), 避免把验证码直接给用户。
"""
from __future__ import annotations

import os
import uuid

import structlog

from app.services.sms.base import SMSProvider, SMSResult

_log = structlog.get_logger("auth.sms.mock")


class MockSMSProvider(SMSProvider):
    """本地开发 / 测试用 SMS Provider。

    短信验证码会:
    1. 写日志 (INFO 级别)
    2. 通过 SMSResult.mock_code 返回, 调用方在 debug 模式打印或推送到调试 UI
    """

    name = "mock"

    def __init__(self, *, expose_code: bool | None = None) -> None:
        # 优先级: 显式参数 > EXPOSE_MOCK_SMS_CODE 环境变量 > APP_ENV 默认
        if expose_code is None:
            flag = os.environ.get("EXPOSE_MOCK_SMS_CODE", "").lower()
            if flag in ("1", "true", "yes", "on"):
                expose_code = True
            else:
                env = os.environ.get("APP_ENV", "development").lower()
                expose_code = env != "production"
        self._expose_code = expose_code

    async def send_code(
        self,
        *,
        phone: str,
        code: str,
        purpose: str,
        ttl_seconds: int,
    ) -> SMSResult:
        message_id = f"mock-{uuid.uuid4().hex[:12]}"
        _log.info(
            "mock_sms_sent",
            phone=phone,
            purpose=purpose,
            ttl_seconds=ttl_seconds,
            message_id=message_id,
            # 不打明文 code 到 INFO, 改 DEBUG
        )
        _log.debug(
            "mock_sms_code_for_debug",
            phone=phone,
            purpose=purpose,
            code=code,
        )
        return SMSResult(
            success=True,
            provider=self.name,
            message_id=message_id,
            mock_code=code if self._expose_code else None,
        )
