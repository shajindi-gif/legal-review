"""工具注册表 - 强校验：未注册工具禁止调用（硬约束 #3）。

设计原则：
1. 工具元信息含 (module, class, version)
2. get_tool(name, version) 通过反射加载，未注册则抛错
3. 注册数据集中维护，便于审计与可观测
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any

from app.core.errors import ValidationError


@dataclass(frozen=True)
class ToolSpec:
    """工具规格。"""
    name: str
    module: str
    class_name: str
    version: str
    description: str = ""


TOOL_REGISTRY: dict[str, ToolSpec] = {
    "ocr_tool": ToolSpec(
        name="ocr_tool",
        module="app.tools.ocr",
        class_name="ocr_image",
        version="v1.0.0",
        description="PaddleOCR 图像识别",
    ),
    "ocr_pdf": ToolSpec(
        name="ocr_pdf",
        module="app.tools.ocr",
        class_name="ocr_pdf_pages",
        version="v1.0.0",
        description="扫描 PDF OCR",
    ),
    "docx_parser": ToolSpec(
        name="docx_parser",
        module="app.tools.parsers",
        class_name="parse_docx",
        version="v1.0.0",
        description="Word 文档解析",
    ),
    "pdf_parser": ToolSpec(
        name="pdf_parser",
        module="app.tools.parsers",
        class_name="parse_pdf_text",
        version="v1.0.0",
        description="数字 PDF 解析",
    ),
    "txt_parser": ToolSpec(
        name="txt_parser",
        module="app.tools.parsers",
        class_name="parse_txt",
        version="v1.0.0",
        description="纯文本解析",
    ),
    "structure_extractor": ToolSpec(
        name="structure_extractor",
        module="app.tools.parsers",
        class_name="parse",
        version="v1.0.0",
        description="文件结构化统一入口",
    ),
    # Sprint 3+ 启用
    "rag_search": ToolSpec(
        name="rag_search",
        module="app.tools.rag",
        class_name="RAGSearchService",
        version="v1.0.0",
        description="RAG 混合检索（向量 + 关键词 + 元数据过滤）",
    ),
    # Sprint 4 启用
    "llm_complete": ToolSpec(
        name="llm_complete",
        module="app.tools.llm",
        class_name="get_llm_provider",
        version="v1.0.0",
        description="LLM 统一接入（DeepSeek-V4-Pro/Flash + Qwen3.7-Max/Plus/Turbo + Mock 可切）",
    ),
    "prompt_manager": ToolSpec(
        name="prompt_manager",
        module="app.services.prompt_manager",
        class_name="get_prompt_manager",
        version="v1.0.0",
        description="Prompt 版本管理（YAML + DB 双源 + 评估门控）",
    ),
    # 以下 Sprint 5+ 启用
    # "evidence_checker": ToolSpec(...),
    # "pdf_renderer": ToolSpec(...),
}


def list_tools() -> list[ToolSpec]:
    """列出全部已注册工具。"""
    return list(TOOL_REGISTRY.values())


def get_tool(name: str, version: str | None = None) -> Any:
    """获取工具实例/函数。

    强校验：未注册工具抛 ValidationError。
    """
    spec = TOOL_REGISTRY.get(name)
    if spec is None:
        raise ValidationError(f"unregistered tool: {name}（硬约束：未注册工具禁止调用）")
    if version is not None and version != spec.version:
        raise ValidationError(
            f"tool version mismatch: requested={version}, registered={spec.version}"
        )

    module = importlib.import_module(spec.module)
    fn = getattr(module, spec.class_name, None)
    if fn is None:
        raise ValidationError(f"tool symbol not found: {spec.module}.{spec.class_name}")
    return fn
