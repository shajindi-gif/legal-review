"""Email Provider 工厂。

按 EMAIL_PROVIDER env / Settings 返回实例:
- mock  → MockEmailProvider (默认, 开发测试)
- smtp  → SmtpEmailProvider (真实 SMTP)
"""
from __future__ import annotations

from app.core.config import get_settings
from app.services.email.base import EmailProvider

_provider_singleton: EmailProvider | None = None


def get_email_provider() -> EmailProvider:
    """根据 settings.email_provider 返回单例 provider。"""
    global _provider_singleton
    if _provider_singleton is not None:
        return _provider_singleton

    settings = get_settings()
    name = settings.email_provider.lower().strip()
    if name == "smtp":
        if not (settings.smtp_host and settings.smtp_from_addr):
            raise RuntimeError(
                "email_provider=smtp 但未配置 smtp_host/smtp_from_addr"
            )
        from app.services.email.smtp import SmtpEmailProvider

        _provider_singleton = SmtpEmailProvider(
            host=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username,
            password=settings.smtp_password,
            from_addr=settings.smtp_from_addr,
            from_name=settings.smtp_from_name,
            use_tls=settings.smtp_use_tls,
        )
    else:
        from app.services.email.mock import MockEmailProvider

        _provider_singleton = MockEmailProvider(
            expose_code=settings.expose_mock_sms_code
            or settings.environment != "prod",
        )
    return _provider_singleton


def reset_email_provider_singleton() -> None:
    """测试用: 重置单例。"""
    global _provider_singleton
    _provider_singleton = None