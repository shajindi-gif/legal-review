"""Citation Verification Engine 单测（离线，不依赖 DB）。"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest

from app.core.constants import LawStatus
from app.schemas.citation import (
    CANNOT_VERIFY_MESSAGE,
    CitationClaim,
    CitationStatus,
)
from app.services.citation_verifier import (
    CitationVerifier,
    ClauseRecord,
    LawRecord,
    classify_text_match,
    classify_validity,
    cn_numeral_to_int,
    normalize_article_no,
    normalize_law_name,
    text_similarity,
)


class FakeLawLookup:
    """内存法规库，供离线核验测试。"""

    def __init__(self, laws: list[LawRecord], clauses: dict[str, ClauseRecord]) -> None:
        # clauses key: f"{law_id}:{normalized_article_no}"
        self._laws = laws
        self._clauses = clauses

    async def find_laws(self, name: str) -> list[LawRecord]:
        return [law for law in self._laws if name in normalize_law_name(law.law_name)]

    async def find_clause(self, law_id, article_no):  # noqa: ANN001, ANN201
        if article_no is None:
            return None
        key = f"{law_id}:{normalize_article_no(article_no)}"
        return self._clauses.get(key)


# ============== 纯函数 ==============

@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("十", 10),
        ("十二", 12),
        ("二十", 20),
        ("一百零一", 101),
        ("一百", 100),
        ("五", 5),
    ],
)
def test_cn_numeral_to_int(raw: str, expected: int) -> None:
    assert cn_numeral_to_int(raw) == expected


def test_cn_numeral_invalid() -> None:
    assert cn_numeral_to_int("abc") is None
    assert cn_numeral_to_int("") is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("第十二条", "12"),
        ("第12条", "12"),
        ("12", "12"),
        (" 第 三 条 ", "3"),
        (None, None),
        ("", None),
    ],
)
def test_normalize_article_no(raw: str | None, expected: str | None) -> None:
    assert normalize_article_no(raw) == expected


def test_normalize_law_name_strips_bookmarks() -> None:
    assert normalize_law_name("《中华人民共和国民法典》") == "中华人民共和国民法典"
    assert normalize_law_name(" 民法典 ") == "民法典"


def test_text_similarity_exact_and_substring() -> None:
    assert text_similarity("完全一致", "完全一致") == 1.0
    # 子串包含视为高吻合
    assert text_similarity("民事主体", "民事主体的人身权利受法律保护") >= 0.95


@pytest.mark.parametrize(
    ("quoted", "matched", "level"),
    [
        (None, "任意", "no_text"),
        ("完全相同", "完全相同", "exact"),
        ("完全不同的内容", "风马牛不相及", "mismatch"),
        ("任意", None, "mismatch"),
    ],
)
def test_classify_text_match(quoted: str | None, matched: str | None, level: str) -> None:
    got, _ = classify_text_match(quoted, matched)
    assert got == level


def test_classify_validity_matrix() -> None:
    as_of = date(2026, 6, 1)
    assert classify_validity(LawStatus.EFFECTIVE, None, None, as_of) == ("effective", True)
    assert classify_validity(LawStatus.AMENDED, None, None, as_of) == ("amended", True)
    assert classify_validity(LawStatus.REPEALED, None, None, as_of) == ("repealed", False)
    assert classify_validity(LawStatus.EXPIRED, None, None, as_of) == ("expired", False)
    assert classify_validity(LawStatus.DRAFT, None, None, as_of) == ("draft", False)
    # 尚未施行
    assert classify_validity(LawStatus.EFFECTIVE, date(2027, 1, 1), None, as_of) == (
        "not_yet_effective", False,
    )
    # 已过期
    assert classify_validity(LawStatus.EFFECTIVE, None, date(2025, 1, 1), as_of) == (
        "expired", False,
    )


# ============== 核验引擎 ==============

def _law(**kw: object) -> LawRecord:
    defaults: dict[str, object] = {
        "id": uuid4(),
        "law_name": "中华人民共和国民法典",
        "law_type": "law",
        "law_level": "national",
        "status": str(LawStatus.EFFECTIVE),
        "effective_date": date(2021, 1, 1),
        "expire_date": None,
        "source_url": "https://flk.npc.gov.cn/x",
        "source_type": "official",
    }
    defaults.update(kw)
    return LawRecord(**defaults)  # type: ignore[arg-type]


@pytest.fixture
def verifier() -> CitationVerifier:
    law = _law()
    clause = ClauseRecord(
        article_no="第十二条",
        content="民事主体的人身权利、财产权利以及其他合法权益受法律保护，任何组织或者个人不得侵犯。",
    )
    lookup = FakeLawLookup([law], {f"{law.id}:12": clause})
    return CitationVerifier(lookup)


async def test_verify_success_exact(verifier: CitationVerifier) -> None:
    res = await verifier.verify(
        CitationClaim(
            law_name="《中华人民共和国民法典》",
            article_no="第12条",
            quoted_text="民事主体的人身权利、财产权利以及其他合法权益受法律保护，任何组织或者个人不得侵犯。",
        )
    )
    assert res.status == CitationStatus.VERIFIED
    assert res.verified is True
    assert res.needs_human_review is False
    assert res.validity == "effective"
    assert res.source_url == "https://flk.npc.gov.cn/x"


async def test_verify_law_not_found(verifier: CitationVerifier) -> None:
    res = await verifier.verify(CitationClaim(law_name="不存在的法典", article_no="第一条"))
    assert res.status == CitationStatus.LAW_NOT_FOUND
    assert res.verified is False
    assert res.needs_human_review is True
    assert "人工复核" in res.message


async def test_verify_article_not_found(verifier: CitationVerifier) -> None:
    res = await verifier.verify(CitationClaim(law_name="民法典", article_no="第九百九十九条"))
    assert res.status == CitationStatus.ARTICLE_NOT_FOUND
    assert res.needs_human_review is True


async def test_verify_text_mismatch(verifier: CitationVerifier) -> None:
    res = await verifier.verify(
        CitationClaim(
            law_name="民法典",
            article_no="12",
            quoted_text="这是一个与真实条文完全不同的伪造内容用于测试不吻合判定。",
        )
    )
    assert res.status == CitationStatus.ARTICLE_TEXT_MISMATCH
    assert res.verified is False
    assert res.text_similarity < 0.9
    assert CANNOT_VERIFY_MESSAGE in res.message


async def test_verify_no_article_no_returns_law_only(verifier: CitationVerifier) -> None:
    res = await verifier.verify(CitationClaim(law_name="民法典"))
    assert res.status == CitationStatus.LAW_ONLY
    assert res.matched_law_name == "中华人民共和国民法典"


async def test_verify_no_quoted_text_is_verified(verifier: CitationVerifier) -> None:
    res = await verifier.verify(CitationClaim(law_name="民法典", article_no="12"))
    assert res.status == CitationStatus.VERIFIED
    assert res.verified is True
    assert res.needs_human_review is False


async def test_verify_repealed_law() -> None:
    law = _law(status=str(LawStatus.REPEALED), effective_date=date(2000, 1, 1))
    verifier = CitationVerifier(FakeLawLookup([law], {}))
    res = await verifier.verify(
        CitationClaim(law_name="民法典", article_no="12", quoted_text="任意")
    )
    assert res.status == CitationStatus.NOT_EFFECTIVE
    assert res.verified is False
    assert "废止" in res.message


async def test_verify_not_yet_effective() -> None:
    law = _law(effective_date=date(2099, 1, 1))
    verifier = CitationVerifier(FakeLawLookup([law], {}))
    res = await verifier.verify(
        CitationClaim(
            law_name="民法典", article_no="12", effective_on=date(2026, 1, 1)
        )
    )
    assert res.status == CitationStatus.NOT_YET_EFFECTIVE
    assert res.validity == "not_yet_effective"


async def test_verify_missing_law_name_is_insufficient() -> None:
    verifier = CitationVerifier(FakeLawLookup([], {}))
    res = await verifier.verify(CitationClaim(law_name="   "))
    assert res.status == CitationStatus.INSUFFICIENT


async def test_verify_many_preserves_order(verifier: CitationVerifier) -> None:
    results = await verifier.verify_many(
        [
            CitationClaim(law_name="民法典", article_no="12"),
            CitationClaim(law_name="不存在的法", article_no="1"),
        ]
    )
    assert results[0].status == CitationStatus.VERIFIED
    assert results[1].status == CitationStatus.LAW_NOT_FOUND
