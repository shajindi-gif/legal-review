"""文件解析工具测试 - FR-004 文本结构化。"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.tools.parsers import parse, parse_txt


def test_parse_txt_basic(tmp_path: Path) -> None:
    content = "标题\n\n第一段内容。\n\n第二段内容。"
    p = tmp_path / "test.txt"
    p.write_text(content, encoding="utf-8")

    result = parse_txt(p)
    assert result["title"] == "标题"
    assert len(result["body_paragraphs"]) == 3
    assert result["body_paragraphs"][0]["text"] == "标题"
    assert result["body_paragraphs"][1]["text"] == "第一段内容。"
    assert result["parser_version"] == "txt.v1.0.0"


def test_parse_txt_empty(tmp_path: Path) -> None:
    p = tmp_path / "empty.txt"
    p.write_text("", encoding="utf-8")

    result = parse_txt(p)
    assert result["title"] is None
    assert result["body_paragraphs"] == []


def test_parse_dispatch_txt(tmp_path: Path) -> None:
    p = tmp_path / "x.txt"
    p.write_text("hello", encoding="utf-8")
    result = parse(p, "txt")
    assert result["parser_version"].startswith("txt")


def test_parse_unsupported_type(tmp_path: Path) -> None:
    p = tmp_path / "x.xyz"
    p.write_text("x", encoding="utf-8")
    from app.core.errors import AgentError

    with pytest.raises(AgentError):
        parse(p, "xyz")
