"""SMTP Email Provider - 真实邮件发送（smtplib 标准库，无额外依赖）。

配置来自 Settings: smtp_host / smtp_port / smtp_username / smtp_password /
smtp_from_addr / smtp_from_name / smtp_use_tls。

验证码场景 M0 仅发送纯文本正文（含验证码 + 有效期提示），不依赖模板引擎。
"""
from __future__ import annotations

import asyncio
import smtplib
import uuid
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr

import structlog

from app.services.email.base import EmailProvider, EmailResult

_log = structlog.get_logger("auth.email.smtp")

_PURPOSE_LABELS = {
    "login": "登录",
    "register": "注册",
    "reset_password": "重置密码",
    "bind_email": "绑定邮箱",
    "change_email": "更换邮箱",
}


class SmtpEmailProvider(EmailProvider):
    """通过 SMTP 发送验证码邮件。"""

    name = "smtp"

    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        from_addr: str,
        from_name: str = "",
        use_tls: bool = True,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._from_addr = from_addr
        self._from_name = from_name
        self._use_tls = use_tls

    def _send_blocking(
        self, *, email: str, code: str, purpose: str, ttl_seconds: int
    ) -> None:
        from_addr = (
            formataddr((Header(self._from_name, "utf-8").encode(), self._from_addr))
            if self._from_name
            else self._from_addr
        )
        minutes = max(1, ttl_seconds // 60)
        subject = f"【智审 · LegalReview】{_PURPOSE_LABELS.get(purpose, '验证')}验证码"
        body = (
            f"您的验证码是：{code}\n"
            f"验证码 {minutes} 分钟内有效，请勿泄露给他人。\n"
            f"若非本人操作，请忽略本邮件。\n"
        )
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = Header(subject, "utf-8").encode()
        msg["From"] = from_addr
        msg["To"] = email

        server: smtplib.SMTP
        if self._use_tls and self._port == 465:
            server = smtplib.SMTP_SSL(self._host, self._port, timeout=15)
        else:
            server = smtplib.SMTP(self._host, self._port, timeout=15)
        try:
            if self._use_tls and self._port != 465:
                server.starttls()
            if self._username:
                server.login(self._username, self._password)
            server.sendmail(self._from_addr, [email], msg.as_string())
        finally:
            server.quit()

    async def send_code(
        self,
        *,
        email: str,
        code: str,
        purpose: str,
        ttl_seconds: int,
    ) -> EmailResult:
        try:
            await asyncio.to_thread(
                self._send_blocking,
                email=email,
                code=code,
                purpose=purpose,
                ttl_seconds=ttl_seconds,
            )
        except Exception as exc:  # noqa: BLE001 - 网络/认证错误统一转失败结果
            _log.error("smtp_send_failed", email=email, error=str(exc)[:160])
            return EmailResult(
                success=False,
                provider=self.name,
                message_id=None,
                error_code=exc.__class__.__name__,
                error_message=str(exc)[:160],
            )
        return EmailResult(
            success=True,
            provider=self.name,
            message_id=f"smtp-{uuid.uuid4().hex[:12]}",
        )