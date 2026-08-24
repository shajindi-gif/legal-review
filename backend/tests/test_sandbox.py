"""沙箱服务测试 - Security Harness 落地校验。

覆盖：
- 扩展名白名单（拒绝 .exe / .js）
- 大小限制
- 路径防逃逸（../../etc/passwd）
- 任务级隔离（任务 A 不能访问任务 B）
- Hash 计算
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import uuid4

import pytest

from app.core.errors import FileTooLargeError, FileTypeError, SandboxError
from app.services.sandbox import SandboxService


@pytest.fixture
def sandbox(tmp_sandbox: Path, monkeypatch: pytest.MonkeyPatch) -> SandboxService:
    """构造一个用 tmp 目录的 SandboxService。"""
    monkeypatch.setattr(
        "app.services.sandbox.get_settings",
        lambda: type(
            "S",
            (),
            {
                "sandbox_path": tmp_sandbox,
                "sandbox_max_file_mb": 1,  # 1MB for test
                "allowed_extensions_set": {"docx", "pdf", "txt", "png", "jpg", "jpeg"},
            },
        )(),
    )
    return SandboxService()


def test_validate_extension_accepts_docx(sandbox: SandboxService) -> None:
    assert sandbox.validate_extension("test.docx") == "docx"


def test_validate_extension_rejects_exe(sandbox: SandboxService) -> None:
    with pytest.raises(FileTypeError):
        sandbox.validate_extension("malware.exe")


def test_validate_size_rejects_oversize(sandbox: SandboxService) -> None:
    with pytest.raises(FileTooLargeError):
        sandbox.validate_size(2 * 1024 * 1024)  # 2MB > 1MB


def test_save_upload_writes_file(sandbox: SandboxService, tmp_sandbox: Path) -> None:
    task_id = uuid4()
    content = b"hello world"
    rel, ftype, size, fhash = sandbox.save_upload(task_id, "doc.txt", content)
    assert ftype == "txt"
    assert size == len(content)
    assert fhash == hashlib.sha256(content).hexdigest()
    # 文件存在
    abs_path = sandbox.absolute_path(task_id, rel)
    assert abs_path.exists()
    assert abs_path.read_bytes() == content


def test_save_upload_rejects_path_traversal(sandbox: SandboxService) -> None:
    task_id = uuid4()
    with pytest.raises(SandboxError):
        sandbox.save_upload(task_id, "../../etc/passwd", b"x")


def test_task_isolation(sandbox: SandboxService) -> None:
    """任务 A 不能读取任务 B 的文件。"""
    task_a, task_b = uuid4(), uuid4()
    sandbox.save_upload(task_a, "secret.txt", b"task_a_secret")
    sandbox.save_upload(task_b, "secret.txt", b"task_b_secret")
    # 任务 A 的 _task_dir 下应该只有自己的 secret.txt
    with pytest.raises(SandboxError):
        # 任务 A 尝试通过 ../{task_b} 逃逸
        sandbox._resolve_safe(task_a, f"../{task_b}/secret.txt")


def test_compute_hash_bytes() -> None:
    content = b"abc"
    expected = hashlib.sha256(content).hexdigest()
    assert SandboxService.compute_hash_bytes(content) == expected


def test_unsafe_filename_sanitized(sandbox: SandboxService) -> None:
    """文件名含危险字符时被 sanitize。"""
    task_id = uuid4()
    # 含 \\ / : * ? 等
    rel, _, _, _ = sandbox.save_upload(task_id, "a:b*c?.txt", b"x")
    # 文件名应不含 : * ?
    abs_path = sandbox.absolute_path(task_id, rel)
    assert ":" not in abs_path.name
    assert "*" not in abs_path.name
