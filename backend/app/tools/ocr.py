"""OCR 工具 - PaddleOCR 封装（中文场景）。

设计：
1. 懒加载 PaddleOCR（首次调用 init，避免启动慢）
2. 输入图像 Path，输出 list[ParagraphItem] 风格段落
3. 异常时降级到空结果，触发人工兜底（不阻断流程）
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.errors import AgentError
from app.core.logging import get_logger

logger = get_logger("tools.ocr")

_ocr_instance = None  # 懒加载单例


def _get_ocr():
    """懒加载 PaddleOCR 实例。"""
    global _ocr_instance
    if _ocr_instance is None:
        try:
            from paddleocr import PaddleOCR

            _ocr_instance = PaddleOCR(
                use_angle_cls=True,
                lang="ch",  # 中文
                show_log=False,
            )
            logger.info("ocr_initialized")
        except ImportError as e:
            raise AgentError(
                "doc_parse",
                f"PaddleOCR not installed: {e}. 安装：pip install paddleocr paddlepaddle",
            ) from e
    return _ocr_instance


def ocr_image(path: Path) -> dict[str, Any]:
    """对图像做 OCR，返回结构化段落。"""
    ocr = _get_ocr()
    try:
        result = ocr.ocr(str(path), cls=True)
    except Exception as e:
        logger.error("ocr_failed", path=str(path), error=str(e))
        raise AgentError("doc_parse", f"OCR failed: {e}") from e

    if not result or not result[0]:
        return {
            "title": None,
            "body_paragraphs": [],
            "parser_version": "ocr.v1.0.0",
            "ocr_warning": "no_text_detected",
        }

    paragraphs = []
    for i, line in enumerate(result[0]):
        # line = (bbox, (text, confidence))，bbox 暂不使用
        text, conf = line[1]
        if text and conf > 0.5:  # 置信度过滤
            paragraphs.append({"id": f"p{i+1}", "text": text, "anchor": f"#p{i+1}"})

    return {
        "title": paragraphs[0]["text"][:255] if paragraphs else None,
        "body_paragraphs": paragraphs,
        "parser_version": "ocr.v1.0.0",
    }


def ocr_pdf_pages(path: Path) -> dict[str, Any]:
    """对扫描 PDF 走 OCR（按页转图）。

    简化实现：使用 pdf2image 把 PDF 转图后调用 ocr_image。
    生产环境建议走商用 OCR API 以提高准确率。
    """
    try:
        from pdf2image import convert_from_path
    except ImportError as e:
        raise AgentError(
            "doc_parse", f"pdf2image not installed: {e}. 安装：pip install pdf2image"
        ) from e

    images = convert_from_path(str(path), dpi=200)
    all_paragraphs = []
    for page_idx, img in enumerate(images):
        # 临时存图，调 ocr
        tmp_path = path.parent / f"_ocr_tmp_p{page_idx+1}.png"
        img.save(tmp_path, "PNG")
        try:
            result = ocr_image(tmp_path)
            for p in result["body_paragraphs"]:
                p["id"] = f"p{page_idx+1}_{p['id']}"
                p["anchor"] = f"#page{page_idx+1}"
                all_paragraphs.append(p)
        finally:
            tmp_path.unlink(missing_ok=True)

    return {
        "title": all_paragraphs[0]["text"][:255] if all_paragraphs else None,
        "body_paragraphs": all_paragraphs,
        "parser_version": "ocr-pdf.v1.0.0",
    }
