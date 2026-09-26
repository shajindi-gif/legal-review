"""Email Provider 包入口。"""
from app.services.email.base import EmailProvider, EmailResult
from app.services.email.factory import get_email_provider, reset_email_provider_singleton
from app.services.email.mock import MockEmailProvider

__all__ = [
    "EmailProvider",
    "EmailResult",
    "MockEmailProvider",
    "get_email_provider",
    "reset_email_provider_singleton",
]