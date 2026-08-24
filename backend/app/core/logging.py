"""结构化日志 - 基于 structlog，注入 trace_id。

设计原则：
- 全局日志器走 structlog，输出 JSON（生产）或 Console（本地）
- 每请求注入 trace_id（FastAPI middleware）
- Agent 节点日志必须带 trace_id / agent_name / iteration
"""

from __future__ import annotations

import logging
import sys

import structlog

from app.core.config import get_settings


def setup_logging() -> None:
    """初始化 structlog + stdlib logging 桥接。"""
    settings = get_settings()
    is_prod = settings.environment in {"prod", "staging"}

    # stdlib logging 桥接
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.INFO,
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            (
                structlog.processors.JSONRenderer()
                if is_prod
                else structlog.dev.ConsoleRenderer(colors=True)
            ),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """获取 logger。"""
    return structlog.get_logger(name)


def bind_trace_id(trace_id: str) -> None:
    """绑定 trace_id 到 contextvar（请求级）。"""
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(trace_id=trace_id)
