"""法规切分器 - 按"第X章/第X节/第X条"原子化切分。

输出 LegalClause 风格 dict，可直接入 legal_clauses 表。

设计原则：
1. 优先识别"第X章 XXXX"→ chapter
2. 识别"第X节 XXXX"→ section
3. 识别"第X条 XXXX"→ article_no + content（核心原子单位）
4. 无章节结构时按"条"切分
5. 保留前言/附则作为单独条款
6. 切分失败时降级为按段落切分
"""

from __future__ import annotations

import re
from typing import Any

from app.core.errors import AgentError
from app.core.logging import get_logger

logger = get_logger("tools.legal_splitter")

# 正则：第X章/节/条，X 支持汉字数字（一二三...）与阿拉伯数字
_CHINESE_NUM = r"[一二三四五六七八九十百千万零0-9]+"
_RE_CHAPTER = re.compile(rf"^第({_CHINESE_NUM})章\s*(.*)$")
_RE_SECTION = re.compile(rf"^第({_CHINESE_NUM})节\s*(.*)$")
_RE_ARTICLE = re.compile(rf"^第({_CHINESE_NUM})条\s*(.*)$")

# 数字转阿拉伯（用于 article_no 标准化，但保留原文也行）
_CHINESE_DIGIT_MAP = {
    "零": "0", "一": "1", "二": "2", "三": "3", "四": "4",
    "五": "5", "六": "6", "七": "7", "八": "8", "九": "9", "十": "10",
}


def normalize_article_no(raw: str) -> str:
    """条款号标准化：保留原文格式，如"第十五条"。"""
    raw = raw.strip()
    if not raw:
        return raw
    # 已含"第X条"格式直接返回
    if raw.startswith("第") and raw.endswith("条"):
        return raw
    return f"第{raw}条"


def split_law(raw_text: str, *, law_name: str = "") -> list[dict[str, Any]]:
    """切分法规全文为条款列表。

    Args:
        raw_text: 法规全文（含章节结构）
        law_name: 法规名（仅用于日志）

    Returns:
        list[dict]，每项含:
        - chapter: 章名（如"总则"）或 None
        - section: 节名 或 None
        - article_no: 条款号（如"第十五条"）
        - article_title: 条款标题（如"【立法目的】"，无则 None）
        - content: 条款正文
        - keywords: []（由调用方填充）
    """
    if not raw_text or not raw_text.strip():
        raise AgentError("legal_retrieve", f"empty law text: {law_name}")

    lines = raw_text.replace("\r\n", "\n").split("\n")
    clauses: list[dict[str, Any]] = []

    current_chapter: str | None = None
    current_section: str | None = None
    current_article: dict[str, Any] | None = None
    current_content_lines: list[str] = []

    def _flush_article() -> None:
        """收尾当前条款。"""
        nonlocal current_article, current_content_lines
        if current_article is not None:
            content = "\n".join(current_content_lines).strip()
            if content:
                current_article["content"] = content
                clauses.append(current_article)
        current_article = None
        current_content_lines = []

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        m_chapter = _RE_CHAPTER.match(line)
        m_section = _RE_SECTION.match(line)
        m_article = _RE_ARTICLE.match(line)

        if m_chapter:
            _flush_article()
            num, title = m_chapter.group(1), m_chapter.group(2).strip()
            current_chapter = f"第{num}章 {title}".strip()
            current_section = None
            logger.debug("chapter_found", chapter=current_chapter, law=law_name)
            continue

        if m_section:
            _flush_article()
            num, title = m_section.group(1), m_section.group(2).strip()
            current_section = f"第{num}节 {title}".strip()
            logger.debug("section_found", section=current_section, law=law_name)
            continue

        if m_article:
            _flush_article()
            num, rest = m_article.group(1), m_article.group(2).strip()
            article_no = f"第{num}条"
            # 条款标题：方括号【】或紧跟的小标题
            article_title: str | None = None
            content_start = rest
            if rest.startswith("【") and "】" in rest:
                end = rest.index("】")
                article_title = rest[1:end]
                content_start = rest[end + 1 :].strip()
            elif rest.startswith("[") and "]" in rest:
                end = rest.index("]")
                article_title = rest[1:end]
                content_start = rest[end + 1 :].strip()

            current_article = {
                "chapter": current_chapter,
                "section": current_section,
                "article_no": article_no,
                "article_title": article_title,
                "content": "",
                "keywords": [],
            }
            current_content_lines = [content_start] if content_start else []
            continue

        # 普通正文行：归入当前条款
        if current_article is not None:
            current_content_lines.append(line)
        else:
            # 前言/附则等无章节结构的内容：作为单独条款保存
            current_article = {
                "chapter": None,
                "section": None,
                "article_no": "前言",
                "article_title": None,
                "content": "",
                "keywords": [],
            }
            current_content_lines = [line]

    _flush_article()

    if not clauses:
        # 切分失败：降级按段落切分
        logger.warning("split_fallback_paragraphs", law=law_name)
        paragraphs = [p.strip() for p in raw_text.split("\n\n") if p.strip()]
        for i, p in enumerate(paragraphs):
            clauses.append({
                "chapter": None,
                "section": None,
                "article_no": f"第{i+1}段",
                "article_title": None,
                "content": p,
                "keywords": [],
            })

    logger.info(
        "law_split_done",
        law=law_name,
        total_clauses=len(clauses),
        chapters=len({c["chapter"] for c in clauses if c["chapter"]}),
    )
    return clauses
