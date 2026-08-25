"""SMS Provider 工厂。

按 SMS_PROVIDER env 返回实例:
- mock      → MockSMSProvider (默认, M0 用)
- tencent   → TencentSMSProvider (M0+ 接入, 留接口)
- aliyun    → AliyunSMSProvider (M0+ 接入, 留接口)
"""
from __future__ import annotations

import os

import structlog

from app.services.sms.base import SMSProvider

_log = structlog.get_logger("auth.sms.factory")

_provider_singleton: SMSProvider | None = None


def get_sms_provider() -> SMSProvider:
    """根据 SMS_PROVIDER env 返回单例 provider。"""
    global _provider_singleton
    if _provider_singleton is not None:
        return _provider_singleton

    name = os.environ.get("SMS_PROVIDER", "mock").lower().strip()
    if name == "mock":
        from app.services.sms.mock import MockSMSProvider
        _provider_singleton = MockSMSProvider()
    elif name == "tencent":
        from app.services.sms.tencent import TencentSMSProvider  # type: ignore[import-not-found]
        _provider_singleton = TencentSMSProvider()
    elif name == "aliyun":
        from app.services.sms.aliyun import AliyunSMSProvider  # type: ignore[import-not-found]
        _provider_singleton = AliyunSMSProvider()
    else:
        _log.warning("unknown_sms_provider_fallback_mock", requested=name)
        from app.services.sms.mock import MockSMSProvider
        _provider_singleton = MockSMSProvider()

    _log.info("sms_provider_loaded", provider=_provider_singleton.name)
    return _provider_singleton


def reset_sms_provider_singleton() -> None:
    """测试用: 重置单例。"""
    global _provider_singleton
    _provider_singleton = None
