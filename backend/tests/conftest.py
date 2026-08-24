"""pytest 公共 fixtures。"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest


@pytest.fixture(scope="session")
def event_loop():
    """session 级 event loop（避免 asyncio_mode=auto 时 loop 提前关闭）。"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
def _stub_audit_log(monkeypatch: pytest.MonkeyPatch):
    """默认把 AuditService.log 桩成 no-op，避免任何 API 测试触碰真实 ORM 审计写入。"""
    from app.services import audit as audit_module

    monkeypatch.setattr(
        audit_module.AuditService, "log", AsyncMock(return_value=None)
    )
    yield


@pytest.fixture
def tmp_sandbox(tmp_path: Path) -> Path:
    """临时沙箱目录。"""
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir(parents=True, exist_ok=True)
    yield sandbox
    shutil.rmtree(sandbox, ignore_errors=True)


@pytest.fixture
def sample_txt_content() -> bytes:
    """构造一份样例规范性文件（TXT）。"""
    return (
        "XX县关于促进中小企业发展的若干意见\n\n"
        "为贯彻落实《中小企业促进法》，结合本县实际，制定本意见。\n\n"
        "一、加大财政支持力度。\n"
        "县财政每年安排专项资金 1000 万元，用于中小企业技术改造。\n\n"
        "二、优化营商环境。\n"
        "除法律法规另有规定外，不得对中小企业设置行政许可前置条件。\n"
    ).encode()


@pytest.fixture
def sample_task_id() -> str:
    return str(uuid4())


@pytest.fixture
def sample_doc_id() -> str:
    return str(uuid4())
