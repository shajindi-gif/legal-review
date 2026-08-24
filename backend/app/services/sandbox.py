"""文件沙箱服务 - 任务级隔离 + 路径防逃逸 + Hash 校验。

硬约束（来自 Security Harness）：
1. 路径必须收敛在 sandbox_root 内（防 ../../etc/passwd）
2. 任务间目录隔离（任务 A 不可访问任务 B 的文件）
3. 文件名 sanitize（禁 \0 / .. / 绝对路径 / 控制字符）
4. 扩展名白名单 + 大小限制
"""

from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path
from uuid import UUID

from app.core.config import get_settings
from app.core.errors import FileTooLargeError, FileTypeError, SandboxError

# 文件名 sanitize 正则：禁 / \ : * ? " < > | \0  及 控制字符
_UNSAFE_NAME_RE = re.compile(r"[\\/\x00-\x1f*?:\"<>|]")


class SandboxService:
    """文件沙箱 - 任务级隔离存储。

    目录结构：
        {sandbox_root}/
            {task_id}/
                {original_sanitized_name}
                {original_sanitized_name}.meta.json
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._root: Path = self._settings.sandbox_path
        self._max_bytes: int = self._settings.sandbox_max_file_mb * 1024 * 1024
        self._allowed_ext: set[str] = self._settings.allowed_extensions_set

    # ============== 路径管理 ==============
    def _task_dir(self, task_id: UUID | str) -> Path:
        """获取任务沙箱目录（不存在则创建）。"""
        safe_id = self._sanitize_name(str(task_id))
        path = (self._root / safe_id).resolve()
        # 防逃逸：resolve 后必须在 root 内
        if not str(path).startswith(str(self._root)):
            raise SandboxError(f"path escape detected: {path}")
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _resolve_safe(self, task_id: UUID | str, filename: str) -> Path:
        """解析任务内文件路径，确保不逃逸。"""
        safe_name = self._sanitize_name(filename)
        task_dir = self._task_dir(task_id)
        path = (task_dir / safe_name).resolve()
        if not str(path).startswith(str(task_dir)):
            raise SandboxError(f"path escape detected: {path}")
        return path

    @staticmethod
    def _sanitize_name(name: str) -> str:
        """文件名 sanitize：去除危险字符，保留原扩展名。

        安全策略：
        1. 空名 → 拒绝
        2. 含 `..`（路径穿越）→ 直接拒绝（即使 basename 处理后不含）
        3. 取 basename，防 `/` 前缀
        4. 替换危险字符（控制字符 / \0 / : * ? 等）
        """
        if not name or not name.strip():
            raise SandboxError("empty filename")
        # 路径穿越直接拒绝（双保险：原始串 + basename 后）
        if ".." in name:
            raise SandboxError(f"path traversal detected: {name}")
        # 取 basename，防 / 前缀
        name = name.replace("\\", "/").split("/")[-1]
        # 替换危险字符
        name = _UNSAFE_NAME_RE.sub("_", name)
        # 双重保险
        if ".." in name:
            raise SandboxError(f"invalid filename: {name}")
        return name

    # ============== 校验 ==============
    def validate_extension(self, filename: str) -> str:
        """扩展名白名单校验，返回小写扩展名。"""
        ext = Path(filename).suffix.lstrip(".").lower()
        if ext not in self._allowed_ext:
            raise FileTypeError(ext, sorted(self._allowed_ext))
        return ext

    def validate_size(self, size_bytes: int) -> None:
        """大小校验。"""
        if size_bytes <= 0:
            raise SandboxError("empty file")
        if size_bytes > self._max_bytes:
            mb = size_bytes / (1024 * 1024)
            raise FileTooLargeError(mb, self._settings.sandbox_max_file_mb)

    # ============== 写入 / 读取 ==============
    def save_upload(
        self, task_id: UUID | str, filename: str, content: bytes
    ) -> tuple[str, str, int, str]:
        """保存上传文件。

        Returns:
            (storage_path_relative, file_type, file_size, file_hash)
            注意：只返回沙箱内相对路径，绝对路径不外泄。

        安全检查顺序（路径逃逸优先于扩展名校验，便于暴露 SandboxError）：
        1. 文件名 sanitize（路径逃逸直接拒绝）
        2. 扩展名白名单
        3. 大小限制
        4. 路径解析（双保险：resolve 后必须收敛在 task_dir 内）
        """
        # 1. 先 sanitize（路径逃逸直接抛 SandboxError）
        safe_name = self._sanitize_name(filename)
        # 2. 扩展名校验（基于 sanitize 后的文件名）
        ext = self.validate_extension(safe_name)
        # 3. 大小校验
        self.validate_size(len(content))
        # 4. 写入
        path = self._resolve_safe(task_id, safe_name)
        path.write_bytes(content)
        file_hash = self.compute_hash_bytes(content)
        file_type = self._map_file_type(ext)

        # 相对路径存储（DB 不存绝对路径，便于迁移）
        rel_path = str(path.relative_to(self._root))
        return rel_path, file_type, len(content), file_hash

    def absolute_path(self, task_id: UUID | str, storage_path_relative: str) -> Path:
        """由相对路径解析绝对路径（用于内部读取，不外泄）。"""
        path = (self._root / storage_path_relative).resolve()
        if not str(path).startswith(str(self._root)):
            raise SandboxError(f"path escape detected: {path}")
        return path

    def read_file(self, task_id: UUID | str, filename: str) -> bytes:
        """读取任务内文件（跨任务访问会因 _task_dir 隔离而失败）。"""
        path = self._resolve_safe(task_id, filename)
        if not path.exists():
            raise SandboxError(f"file not found: {filename}")
        return path.read_bytes()

    def delete_task_dir(self, task_id: UUID | str) -> None:
        """清理任务沙箱（任务删除时调用）。"""
        task_dir = self._task_dir(task_id)
        shutil.rmtree(task_dir, ignore_errors=True)

    # ============== Hash ==============
    @staticmethod
    def compute_hash_bytes(content: bytes) -> str:
        """计算 SHA-256。"""
        return hashlib.sha256(content).hexdigest()

    @staticmethod
    def compute_hash_file(path: Path) -> str:
        """计算文件 SHA-256（流式）。"""
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    # ============== 类型映射 ==============
    @staticmethod
    def _map_file_type(ext: str) -> str:
        """扩展名 → FileType 枚举值。"""
        mapping = {
            "docx": "docx",
            "pdf": "pdf",
            "txt": "txt",
            "png": "image",
            "jpg": "image",
            "jpeg": "image",
        }
        return mapping.get(ext, "txt")


_sandbox: SandboxService | None = None


def get_sandbox() -> SandboxService:
    """单例。"""
    global _sandbox
    if _sandbox is None:
        _sandbox = SandboxService()
    return _sandbox
