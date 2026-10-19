"""法律依据核验引擎（Citation Verification Engine）。

PHASE 1 核心差异化能力：回答中的每一条法律依据都必须可核验，杜绝编造。

设计原则（对应总指令）：
1. 名称、条款编号、引用原文、时效 四要素逐项核验，任一不通过即不可宣称「已核实」。
2. 不做「文本相似度即法律效力」的混淆；相似度仅用于判断引用原文是否吻合。
3. 无法核验时返回明确状态 + 统一提示「暂未找到可核验的权威依据，需要人工复核。」
4. 核验核心为确定性算法（不依赖 LLM），可离线单测；DB 访问通过 LawLookup 抽象注入。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from difflib import SequenceMatcher
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import LawStatus
from app.core.logging import get_logger
from app.models.legal import LegalClause, LegalDocument
from app.schemas.citation import (
    CANNOT_VERIFY_MESSAGE,
    CitationClaim,
    CitationStatus,
    CitationVerificationResult,
)

logger = get_logger("services.citation_verifier")

# 名称匹配接受的相似度下限：低于此值视为「法规名称不存在」
_LAW_NAME_MIN_SIMILARITY = 0.85
# 引用原文「吻合」的相似度下限（低于此值判为 text_mismatch）
_TEXT_EXACT_MIN_SIMILARITY = 0.999
_TEXT_NEAR_MIN_SIMILARITY = 0.90

_CN_DIGITS: dict[str, int] = {
    "零": 0, "〇": 0,
    "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9,
    "十": 10, "百": 100,
}


# ============== 纯函数：文本 / 编号归一化 ==============

def normalize_law_name(raw: str) -> str:
    """法规名称归一化：去掉书名号、空白与全角标点。"""
    s = raw.strip()
    for ch in ("《", "》", "〈", "〉", " ", "\u3000", "\t", "\n"):
        s = s.replace(ch, "")
    return s


def normalize_article_no(raw: str | None) -> str | None:
    """条款编号归一化：把「第十二条」「第12条」「12」统一为阿拉伯数字串「12」。

    无法解析为数字时返回去空白的原文（如「第一百零一条之二」降级为原文比对）。
    """
    if raw is None:
        return None
    s = raw.strip()
    if not s:
        return None
    for ch in (" ", "\u3000", "第", "条", "款", "项", "节"):
        s = s.replace(ch, "")
    if s.isdigit():
        return str(int(s))
    if all(c in _CN_DIGITS for c in s) and s:
        val = cn_numeral_to_int(s)
        if val is not None:
            return str(val)
    return s


def cn_numeral_to_int(s: str) -> int | None:
    """中文数字转整数（支持到 999），如「一百零一」→ 101。无法解析返回 None。"""
    if not s:
        return None
    total = 0
    section = 0
    number = 0
    for ch in s:
        if ch not in _CN_DIGITS:
            return None
        digit = _CN_DIGITS[ch]
        if digit < 10:
            number = digit
        elif digit == 10:
            section += (number or 1) * 10
            number = 0
        elif digit == 100:
            section += (number or 1) * 100
            number = 0
    total = section + number
    return total or None


def normalize_text(raw: str) -> str:
    """条文正文归一化：合并空白、统一全角/半角、去掉常见标点差异。"""
    s = raw.strip()
    s = re.sub(r"\s+", "", s)
    trans = str.maketrans(
        "０１２３４５６７８９（）【】《》，。；：、“”‘’", 
        "0123456789()[]<>,.;:,\"\"''",
    )
    return s.translate(trans)


def text_similarity(a: str, b: str) -> float:
    """归一化文本相似度（0~1）。"""
    na, nb = normalize_text(a), normalize_text(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    if na in nb or nb in na:
        # 引用往往是条文子串，子串包含视为高吻合
        ratio = min(len(na), len(nb)) / max(len(na), len(nb))
        return round(0.95 + 0.05 * ratio, 4)
    return round(SequenceMatcher(None, na, nb).ratio(), 4)


def classify_text_match(quoted: str | None, matched: str | None) -> tuple[str, float]:
    """判定引用原文与库内条文的吻合度。

    返回 (level, similarity)：level ∈ {"exact","near","weak","mismatch","no_text"}
    """
    if not quoted:
        return "no_text", 0.0
    if not matched:
        return "mismatch", 0.0
    sim = text_similarity(quoted, matched)
    if sim >= _TEXT_EXACT_MIN_SIMILARITY:
        return "exact", sim
    if sim >= _TEXT_NEAR_MIN_SIMILARITY:
        return "near", sim
    if sim >= 0.6:
        return "weak", sim
    return "mismatch", sim


def classify_validity(
    status: str,
    effective_date: date | None,
    expire_date: date | None,
    as_of: date,
) -> tuple[str, bool]:
    """时效性判定。返回 (validity_code, is_effective)。"""
    st = str(status)
    if st == str(LawStatus.REPEALED):
        return "repealed", False
    if st == str(LawStatus.EXPIRED):
        return "expired", False
    if st == str(LawStatus.DRAFT):
        return "draft", False
    if effective_date is not None and as_of < effective_date:
        return "not_yet_effective", False
    if expire_date is not None and as_of > expire_date:
        return "expired", False
    if st == str(LawStatus.EFFECTIVE):
        return "effective", True
    if st == str(LawStatus.AMENDED):
        return "amended", True
    return "unknown", False


# ============== 数据访问抽象（可注入假实现做离线单测）==============
@dataclass(frozen=True)
class LawRecord:
    """法规记录（与 ORM 解耦）。"""

    id: UUID
    law_name: str
    law_type: str
    law_level: str
    status: str
    effective_date: date | None
    expire_date: date | None
    source_url: str | None = None
    source_type: str | None = None


@dataclass(frozen=True)
class ClauseRecord:
    """条款记录。"""

    article_no: str
    content: str
    chapter: str | None = None
    section: str | None = None


@dataclass(frozen=True)
class CitationLawContext:
    """核验结果中的法规级字段集合（供 _result 统一填充）。"""

    matched_law_name: str | None = None
    matched_article_no: str | None = None
    matched_text: str | None = None
    text_similarity: float = 0.0
    source_url: str | None = None
    source_type: str | None = None
    validity: str = "unknown"


class LawLookup(Protocol):
    """法规检索抽象：DB 实现 / 测试假实现。"""

    async def find_laws(self, name: str) -> list[LawRecord]: ...

    async def find_clause(self, law_id: UUID, article_no: str | None) -> ClauseRecord | None: ...


class DbLawLookup:
    """基于 PostgreSQL 法规库的检索实现。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_laws(self, name: str) -> list[LawRecord]:
        stmt = (
            select(LegalDocument)
            .where(
                LegalDocument.deleted_at.is_(None),
                LegalDocument.law_name.ilike(f"%{name}%"),
            )
            .limit(20)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [
            LawRecord(
                id=row.id,
                law_name=row.law_name,
                law_type=str(row.law_type),
                law_level=str(row.law_level),
                status=str(row.status),
                effective_date=row.effective_date,
                expire_date=row.expire_date,
                source_url=getattr(row, "source_url", None),
                source_type=getattr(row, "source_type", None),
            )
            for row in rows
        ]

    async def find_clause(self, law_id: UUID, article_no: str | None) -> ClauseRecord | None:
        if article_no is None:
            return None
        normalized = normalize_article_no(article_no)
        stmt = select(LegalClause).where(LegalClause.law_id == law_id)
        rows = (await self._session.execute(stmt)).scalars().all()
        for row in rows:
            if normalize_article_no(row.article_no) == normalized:
                return ClauseRecord(
                    article_no=row.article_no,
                    content=row.content,
                    chapter=row.chapter,
                    section=row.section,
                )
        return None


# ============== 核验引擎 ==============
class CitationVerifier:
    """法律依据核验引擎。

    用法：
        verifier = CitationVerifier(DbLawLookup(session))
        result = await verifier.verify(CitationClaim(law_name="民法典", article_no="第十二条"))
    """

    def __init__(self, lookup: LawLookup) -> None:
        self._lookup = lookup

    async def verify(self, claim: CitationClaim) -> CitationVerificationResult:
        """核验单条引用。"""
        as_of = claim.effective_on or datetime.now(UTC).date()
        checked_at = datetime.now(UTC)

        name = normalize_law_name(claim.law_name)
        if not name:
            return self._result(
                claim, CitationStatus.INSUFFICIENT, checked_at,
                message="引用缺少法规名称，无法核验。" + CANNOT_VERIFY_MESSAGE,
            )

        # 1. 法规名称匹配
        candidates = await self._lookup.find_laws(name)
        law = self._pick_law(name, candidates)
        if law is None:
            logger.info("citation_law_not_found", law_name=claim.law_name)
            return self._result(
                claim, CitationStatus.LAW_NOT_FOUND, checked_at,
                validity="unknown",
                message=f"法规「{claim.law_name}」在法规库中不存在。" + CANNOT_VERIFY_MESSAGE,
            )

        # 2. 时效性
        validity, is_effective = classify_validity(
            law.status, law.effective_date, law.expire_date, as_of
        )
        ctx = CitationLawContext(
            matched_law_name=law.law_name,
            source_url=law.source_url,
            source_type=law.source_type,
            validity=validity,
        )

        if validity == "repealed":
            return self._result(
                claim, CitationStatus.NOT_EFFECTIVE, checked_at, ctx=ctx,
                message=f"「{law.law_name}」已废止，不得作为现行依据。{CANNOT_VERIFY_MESSAGE}",
            )
        if validity == "not_yet_effective":
            eff = law.effective_date.isoformat() if law.effective_date else "未知"
            return self._result(
                claim, CitationStatus.NOT_YET_EFFECTIVE, checked_at, ctx=ctx,
                message=f"截至 {as_of.isoformat()}，「{law.law_name}」尚未施行（生效日 {eff}）。",
            )
        if validity == "expired":
            return self._result(
                claim, CitationStatus.EXPIRED, checked_at, ctx=ctx,
                message=f"「{law.law_name}」已过有效期。{CANNOT_VERIFY_MESSAGE}",
            )

        # 3. 条款定位
        if normalize_article_no(claim.article_no) is None:
            # 未提供条号：法规存在但无法定位条款
            return self._result(
                claim, CitationStatus.LAW_ONLY, checked_at, ctx=ctx,
                message=f"已定位法规「{law.law_name}」，但未提供条款编号，无法核验具体条文。",
            )
        clause = await self._lookup.find_clause(law.id, claim.article_no)
        if clause is None:
            return self._result(
                claim, CitationStatus.ARTICLE_NOT_FOUND, checked_at, ctx=ctx,
                message=f"「{law.law_name}」中未找到 {claim.article_no}。{CANNOT_VERIFY_MESSAGE}",
            )

        # 4. 原文吻合度
        level, sim = classify_text_match(claim.quoted_text, clause.content)
        ctx = CitationLawContext(
            matched_law_name=law.law_name,
            matched_article_no=clause.article_no,
            matched_text=clause.content,
            text_similarity=sim,
            source_url=law.source_url,
            source_type=law.source_type,
            validity=validity,
        )
        if level == "no_text":
            # 未引用原文：可核验到条款层
            return self._result(
                claim, CitationStatus.VERIFIED, checked_at, ctx=ctx,
                message=f"已核验「{law.law_name}」{clause.article_no} 存在且现行有效。",
                verified=True, needs_human_review=not is_effective,
            )
        if level in ("exact", "near", "weak"):
            return self._result(
                claim, CitationStatus.VERIFIED, checked_at, ctx=ctx,
                message=(
                    f"已核验「{law.law_name}」{clause.article_no} 存在，"
                    f"引用原文吻合（相似度 {sim:.2f}）。"
                ),
                verified=True, needs_human_review=level != "exact",
            )
        return self._result(
            claim, CitationStatus.ARTICLE_TEXT_MISMATCH, checked_at, ctx=ctx,
            message=(
                f"「{law.law_name}」{clause.article_no} 存在，但引用原文与库内条文不一致"
                f"（相似度 {sim:.2f}）。{CANNOT_VERIFY_MESSAGE}"
            ),
        )

    async def verify_many(self, claims: list[CitationClaim]) -> list[CitationVerificationResult]:
        """批量核验（保持顺序）。"""
        return [await self.verify(c) for c in claims]

    # ---- 内部 ----
    @staticmethod
    def _pick_law(name: str, candidates: list[LawRecord]) -> LawRecord | None:
        """从候选中挑选最佳名称匹配。

        优先级：归一化等值 > 名称包含（简称，如「民法典」⊂「中华人民共和国民法典」）
        > 相似度达阈值。包含匹配在中文法律实践中是常态（简称/全称互换）。
        """
        exact: LawRecord | None = None
        contained: LawRecord | None = None
        sim_best: LawRecord | None = None
        sim_best_val = 0.0
        for cand in candidates:
            cn = normalize_law_name(cand.law_name)
            if cn == name:
                exact = cand
                break
            if (name in cn or cn in name) and (
                contained is None or len(cn) < len(normalize_law_name(contained.law_name))
            ):
                contained = cand
            sim = SequenceMatcher(None, cn, name).ratio()
            if sim > sim_best_val:
                sim_best_val, sim_best = sim, cand
        if exact is not None:
            return exact
        if contained is not None:
            return contained
        if sim_best is not None and sim_best_val >= _LAW_NAME_MIN_SIMILARITY:
            return sim_best
        return None

    @staticmethod
    def _result(
        claim: CitationClaim,
        status: CitationStatus,
        checked_at: datetime,
        *,
        message: str,
        verified: bool = False,
        needs_human_review: bool = True,
        validity: str = "unknown",
        ctx: CitationLawContext | None = None,
    ) -> CitationVerificationResult:
        c = ctx or CitationLawContext()
        return CitationVerificationResult(
            status=status,
            verified=verified,
            needs_human_review=needs_human_review,
            law_name=claim.law_name,
            article_no=claim.article_no,
            quoted_text=claim.quoted_text,
            matched_law_name=c.matched_law_name,
            matched_article_no=c.matched_article_no,
            matched_text=c.matched_text,
            text_similarity=c.text_similarity,
            validity=validity if ctx is None else c.validity,
            source_url=c.source_url,
            source_type=c.source_type,
            message=message,
            checked_at=checked_at,
        )
