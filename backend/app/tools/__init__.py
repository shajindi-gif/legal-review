"""工具集合入口。"""

from app.tools.ocr import ocr_image, ocr_pdf_pages
from app.tools.parsers import (
    detect_parser,
    parse,
    parse_docx,
    parse_pdf_text,
    parse_txt,
)
from app.tools.registry import ToolSpec, get_tool, list_tools

__all__ = [
    "ToolSpec",
    "detect_parser",
    "get_tool",
    "list_tools",
    "ocr_image",
    "ocr_pdf_pages",
    "parse",
    "parse_docx",
    "parse_pdf_text",
    "parse_txt",
]
