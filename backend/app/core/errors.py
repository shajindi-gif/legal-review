"""应用异常体系 + 统一错误响应。

设计原则：
- 业务异常继承 AppError，携带 trace_id/err_code/http_status
- 全局异常处理器在 main.py 注册，输出统一 envelope
- 不暴露内部堆栈给客户端
"""

from __future__ import annotations

from uuid import uuid4


class AppError(Exception):
    """应用基类异常。"""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        http_status: int = 400,
        trace_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.trace_id = trace_id or str(uuid4())


class NotFoundError(AppError):
    """资源不存在。

    兼容两种调用方式：
    - NotFoundError("ReviewTask", str(task_id))  → "ReviewTask not found: <id>"
    - NotFoundError("用户不存在")               → "用户不存在"
    """

    def __init__(
        self,
        resource_or_msg: str,
        resource_id: str = "",
        *,
        message: str = "",
    ) -> None:
        if message:
            msg = message
        elif resource_id:
            msg = f"{resource_or_msg} not found: {resource_id}"
        else:
            msg = resource_or_msg
        super().__init__(
            code="not_found",
            message=msg,
            http_status=404,
        )


class ConflictError(AppError):
    """资源冲突（如邮箱已注册）。"""

    def __init__(self, message: str) -> None:
        super().__init__(code="conflict", message=message, http_status=409)


class AuthError(AppError):
    """鉴权失败（登录失败 / token 无效）。"""

    def __init__(self, message: str) -> None:
        super().__init__(code="auth_error", message=message, http_status=401)


class QuotaExceededError(AppError):
    """配额超限（Free 用户每日审查上限）。"""

    def __init__(self, message: str) -> None:
        super().__init__(code="quota_exceeded", message=message, http_status=429)


class ValidationError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(code="validation_error", message=message, http_status=422)


class FileTypeError(ValidationError):
    def __init__(self, ext: str, allowed: list[str]) -> None:
        super().__init__(
            f"Unsupported file type: {ext}. Allowed: {', '.join(allowed)}",
        )
        self.code = "file_type_error"


class FileTooLargeError(ValidationError):
    def __init__(self, size_mb: float, max_mb: int) -> None:
        super().__init__(
            f"File too large: {size_mb:.1f}MB > {max_mb}MB",
        )
        self.code = "file_too_large"


class SandboxError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(code="sandbox_error", message=message, http_status=500)


class AgentError(AppError):
    def __init__(self, agent: str, message: str, *, trace_id: str | None = None) -> None:
        super().__init__(
            code=f"agent_error.{agent}",
            message=f"[{agent}] {message}",
            http_status=500,
            trace_id=trace_id,
        )


class IterationLimitExceededError(AgentError):
    """Agent 循环超限（硬约束触发）。"""

    def __init__(self, agent: str, max_iter: int, *, trace_id: str | None = None) -> None:
        super().__init__(
            agent=agent,
            message=f"iteration limit exceeded: {max_iter}",
            trace_id=trace_id,
        )


def error_response(exc: AppError) -> dict:
    """统一错误响应 envelope。"""
    return {
        "error": {
            "code": exc.code,
            "message": exc.message,
            "trace_id": exc.trace_id,
        }
    }
