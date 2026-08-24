"""法规切分器测试 - Sprint 3 / FR-013 原子化切分。

覆盖：
- 完整章节 + 节 + 条款结构
- 仅条款结构（无章节）
- 条款标题【方括号】
- 前言/附则（无章节结构的杂项内容）
- 空文本与降级路径
- 数字与汉字数字混用
"""
from __future__ import annotations

import pytest

from app.core.errors import AgentError
from app.tools.legal_splitter import normalize_article_no, split_law


# ============== 完整结构 ==============
def test_split_full_chapter_section_article() -> None:
    """章/节/条 三层结构切分。"""
    raw = """第一章 总则
第一节 立法目的
第一条 【立法目的】为了规范行政规范性文件制定程序，制定本法。
第二条 任何单位不得违法设置行政许可。

第二章 实体规定
第三条 本法所称行政规范性文件，是指除政府规章外的文件。
"""
    clauses = split_law(raw, law_name="测试法")

    assert len(clauses) == 3
    # 第一条
    c1 = clauses[0]
    assert c1["chapter"] == "第一章 总则"
    assert c1["section"] == "第一节 立法目的"
    assert c1["article_no"] == "第一条"
    assert c1["article_title"] == "立法目的"
    assert "为了规范行政规范性文件制定程序" in c1["content"]
    assert c1["keywords"] == []
    # 第二条：同章同节
    c2 = clauses[1]
    assert c2["chapter"] == "第一章 总则"
    assert c2["section"] == "第一节 立法目的"
    assert c2["article_no"] == "第二条"
    assert c2["article_title"] is None
    # 第三条：新章节，无节
    c3 = clauses[2]
    assert c3["chapter"] == "第二章 实体规定"
    assert c3["section"] is None
    assert c3["article_no"] == "第三条"


def test_split_chapter_carried_until_next_chapter() -> None:
    """章上下文跨节持续，直到下一个章出现。"""
    raw = """第一章 总则
第一条 内容一。
第二条 内容二。
第二章 附则
第三条 内容三。
"""
    clauses = split_law(raw)
    assert len(clauses) == 3
    assert clauses[0]["chapter"] == "第一章 总则"
    assert clauses[1]["chapter"] == "第一章 总则"
    assert clauses[2]["chapter"] == "第二章 附则"


# ============== 仅条款结构 ==============
def test_split_articles_only_no_chapter() -> None:
    """无章节，仅按"第X条"切分。"""
    raw = """第一条 内容一。
第二条 内容二。
第三条 内容三。
"""
    clauses = split_law(raw, law_name="简单法")
    assert len(clauses) == 3
    assert all(c["chapter"] is None for c in clauses)
    assert all(c["section"] is None for c in clauses)
    assert [c["article_no"] for c in clauses] == ["第一条", "第二条", "第三条"]


def test_split_article_with_brackets_title() -> None:
    """【方括号】识别为 article_title。"""
    raw = "第一条 【适用范围】本法适用于全县。"
    clauses = split_law(raw)
    assert len(clauses) == 1
    assert clauses[0]["article_title"] == "适用范围"
    assert "本法适用于全县" in clauses[0]["content"]


def test_split_article_with_square_brackets_title() -> None:
    """半角 [] 也识别为 article_title。"""
    raw = "第一条 [适用范围] 本法适用于全县。"
    clauses = split_law(raw)
    assert len(clauses) == 1
    assert clauses[0]["article_title"] == "适用范围"


# ============== 前言/杂项内容 ==============
def test_split_preface_as_separate_clause() -> None:
    """前言（无章节结构的引言）作为单独条款。"""
    raw = """本法规由 XX 县人民政府发布。
第一条 正文一。
"""
    clauses = split_law(raw)
    assert len(clauses) == 2
    # 第一行作为前言
    assert clauses[0]["article_no"] == "前言"
    assert clauses[0]["chapter"] is None
    assert "由 XX 县人民政府发布" in clauses[0]["content"]
    # 第二条是正式条款
    assert clauses[1]["article_no"] == "第一条"


# ============== 数字格式 ==============
def test_split_arabic_numerals() -> None:
    """阿拉伯数字编号也能识别。"""
    raw = """第1条 内容一。
第2条 内容二。"""
    clauses = split_law(raw)
    assert len(clauses) == 2
    assert clauses[0]["article_no"] == "第1条"
    assert clauses[1]["article_no"] == "第2条"


def test_split_chinese_numerals() -> None:
    """汉字数字编号。"""
    raw = """第十条 内容一。
第十五条 内容二。
第二十条 内容三。"""
    clauses = split_law(raw)
    assert len(clauses) == 3
    assert clauses[1]["article_no"] == "第十五条"


# ============== 多行条款内容 ==============
def test_split_multiline_article_content() -> None:
    """条款正文跨多行应合并。"""
    raw = """第一条 本条规定如下：
（一）第一项内容；
（二）第二项内容；
（三）第三项内容。"""
    clauses = split_law(raw)
    assert len(clauses) == 1
    content = clauses[0]["content"]
    assert "本条规定如下" in content
    assert "第一项内容" in content
    assert "第三项内容" in content
    # 多行被 \n 连接
    assert "\n" in content


# ============== 空与异常 ==============
def test_split_empty_text_raises() -> None:
    """空文本必须抛 AgentError。"""
    with pytest.raises(AgentError):
        split_law("")


def test_split_whitespace_only_raises() -> None:
    """仅空白也抛 AgentError。"""
    with pytest.raises(AgentError):
        split_law("   \n  \n  ")


def test_split_plain_paragraphs_become_single_preface() -> None:
    """无任何章节/条款结构的纯文本 → 归并到单一"前言"条款。

    实现行为：解析时 current_article 为 None 的第一行普通文本会被收为"前言"条款，
    后续普通文本行继续并入该前言（多行用 \\n 连接）。
    因此纯段落文本不会触发按段切分的 fallback（fallback 仅在 clauses 列表为空时触发，
    而只要存在非空行就会创建前言条款，clauses 永远非空 → fallback 路径实际不可达）。
    """
    raw = """这是第一段内容，没有条款结构。

这是第二段内容，仍然没有条款结构。

这是第三段。"""
    clauses = split_law(raw, law_name="无结构文")
    assert len(clauses) == 1
    assert clauses[0]["article_no"] == "前言"
    assert clauses[0]["chapter"] is None
    assert clauses[0]["section"] is None
    content = clauses[0]["content"]
    assert "第一段内容" in content
    assert "第二段内容" in content
    assert "第三段" in content


def test_split_crlf_normalized() -> None:
    r"""\r\n 应被规范化为 \n 后再切分。"""
    raw = "第一条 内容一。\r\n第二条 内容二。\r\n"
    clauses = split_law(raw)
    assert len(clauses) == 2
    assert "内容一" in clauses[0]["content"]
    assert "\r" not in clauses[0]["content"]


def test_split_empty_lines_ignored() -> None:
    """空行不影响切分。"""
    raw = """

第一条 内容一。



第二条 内容二。
"""
    clauses = split_law(raw)
    assert len(clauses) == 2
    assert clauses[0]["article_no"] == "第一条"


# ============== normalize_article_no ==============
def test_normalize_article_no_already_formatted() -> None:
    """已含"第X条"格式直接返回。"""
    assert normalize_article_no("第十五条") == "第十五条"
    assert normalize_article_no("第1条") == "第1条"


def test_normalize_article_no_plain_number() -> None:
    """纯数字自动补全。"""
    assert normalize_article_no("十五") == "第十五条"
    assert normalize_article_no("1") == "第1条"


def test_normalize_article_no_empty() -> None:
    """空串 / 纯空白 strip 后返回空。"""
    assert normalize_article_no("") == ""
    # 纯空白会被 strip 成空串
    assert normalize_article_no("   ") == ""
