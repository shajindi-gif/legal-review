"""SMS Provider 抽象基类 + 数据结构。

实现:
- base.py         Protocol + SMSResult
- mock.py         MockSMSProvider (开发 + 测试)
- factory.py      get_sms_provider() 根据 SMS_PROVIDER env 切换
- (后续) tencent.py / aliyun.py
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SMSResult:
    """SMS 发送结果。"""

    success: bool
    provider: str
    message_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    mock_code: str | None = None  # Mock 模式下携带验证码, 方便开发联调 (生产 mock 关闭)


class SMSProvider(Protocol):
    """SMS Provider 协议。

    实现要求:
    - send_code 必须返回 SMSResult
    - 失败时不抛异常, 通过 success=False 表达
    - 不打日志包含明文验证码 (用 mock_code 字段传递)
    """

    name: str

    async def send_code(
        self,
        *,
        phone: str,
        code: str,
        purpose: str,
        ttl_seconds: int,
    ) -> SMSResult: ...
