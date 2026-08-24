"""法规库服务测试 - Sprint 3 / FR-013/014/016。

覆盖：
- import_law：切分 + embedding + ORM 构造（mock session/embedding）
- import_law：embedding 数量不匹配时抛 AgentError
- import_law：无 effective_date 默认 status=effective
- import_law：effective_date 在未来时 status=draft
- check_time_validity：未生效 / 已过期 / 即将过期 / 30天内警告
- update_law_status：状态变更 + 修订链 parent_law_id
- get_law_with_clauses：未找到抛 NotFoundError
- list_laws：分页 + 元数据过滤
- batch_import：单条失败不影响其他（容错）
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import LawLevel, LawStatus, LawType
from app.core.errors import AgentError, NotFoundError
from app.schemas.legal import LegalDocumentCreate
from app.services import legal_library
from app.services.legal_library import LegalLibraryService

# ============== 测试数据 ==============
SAMPLE_LAW_TEXT = """第一章 总则
第一条 【立法目的】为了规范行政许可的设定和实施，制定本法。
第二条 本法适用范围。

第二章 实体规定
第三条 行政许可的设定应当遵循法定职权。
"""


def _make_create_req(
    *,
    law_name: str = "行政许可法",
    raw_text: str = SAMPLE_LAW_TEXT,
    effective_date: date | None = None,
    expire_date: date | None = None,
) -> LegalDocumentCreate:
    return LegalDocumentCreate(
        law_name=law_name,
        issuing_authority="全国人大常委会",
        publish_date=date(2024, 1, 1),
        effective_date=effective_date,
        expire_date=expire_date,
        law_type=LawType.LAW,
        law_level=LawLevel.NATIONAL,
        version="v1.0.0",
        raw_text=raw_text,
        keywords=["行政许可", "立法"],
    )


def _mock_session() -> AsyncMock:
    """构造一个 mock AsyncSession。

    flush 时自动给新加入的 LegalDocument / LegalClause 对象赋 UUID，
    模拟真实数据库的 server_default=uuid4 行为（否则 law.id 为 None）。
    """
    session = AsyncMock(spec=AsyncSession)
    added_objects: list[Any] = []

    def _add(obj: Any) -> None:
        added_objects.append(obj)

    async def _flush() -> None:
        from uuid import uuid4

        from app.models.legal import LegalDocument
        for obj in added_objects:
            if isinstance(obj, LegalDocument) and getattr(obj, "id", None) is None:
                obj.id = uuid4()

    session.add = MagicMock(side_effect=_add)
    session.flush = AsyncMock(side_effect=_flush)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.execute = AsyncMock()
    return session


def _mock_embedding_provider() -> Any:
    """构造一个 mock embedding provider（同步调用返回，不阻塞）。

    注意：get_embedding_provider() 是同步函数，所以 mock 必须返回
    provider 对象本身，而不是 AsyncMock（AsyncMock 调用会返回 coroutine）。
    """
    provider = MagicMock()
    provider.name = "mock"
    provider.dim = 1024

    async def _batch_embed(texts: list[str]) -> list[list[float]]:
        return [[0.1] * 1024 for _ in texts]

    provider.batch_embed = _batch_embed
    return provider


def _patch_provider(provider: Any) -> Any:
    """返回一个 patch 上下文，让 get_embedding_provider() 同步返回 provider。"""
    return patch.object(legal_library, "get_embedding_provider", lambda: provider)


# ============== import_law ==============
@pytest.mark.asyncio
async def test_import_law_success() -> None:
    """成功导入：切分 → embedding → ORM 构造。"""
    session = _mock_session()
    service = LegalLibraryService(session)

    with _patch_provider(_mock_embedding_provider()):
        law = await service.import_law(_make_create_req())

    # flush 至少调用 2 次（一次拿 law.id，一次拿 clauses）
    assert session.flush.await_count >= 2
    # add 至少调用 1 + N 次（1 个 law + N 个 clause）
    assert session.add.call_count >= 1
    # 返回的是 LegalDocument
    from app.models.legal import LegalDocument
    assert isinstance(law, LegalDocument)
    assert law.law_name == "行政许可法"
    assert law.law_type == "law"
    assert law.law_level == "national"
    assert law.version == "v1.0.0"
    # 默认 effective_date=None → status = effective
    assert law.status == LawStatus.EFFECTIVE.value


@pytest.mark.asyncio
async def test_import_law_default_status_effective_when_no_effective_date() -> None:
    """未指定 effective_date → status=effective。"""
    session = _mock_session()
    service = LegalLibraryService(session)

    with _patch_provider(_mock_embedding_provider()):
        law = await service.import_law(_make_create_req(effective_date=None))

    assert law.status == LawStatus.EFFECTIVE.value


@pytest.mark.asyncio
async def test_import_law_status_draft_when_future_effective_date() -> None:
    """effective_date 在未来 → status=draft。"""
    session = _mock_session()
    service = LegalLibraryService(session)

    future_date = date.today() + timedelta(days=30)
    with _patch_provider(_mock_embedding_provider()):
        law = await service.import_law(_make_create_req(effective_date=future_date))

    assert law.status == LawStatus.DRAFT.value


@pytest.mark.asyncio
async def test_import_law_status_effective_when_past_effective_date() -> None:
    """effective_date 在过去 → status=effective。"""
    session = _mock_session()
    service = LegalLibraryService(session)

    past_date = date.today() - timedelta(days=30)
    with _patch_provider(_mock_embedding_provider()):
        law = await service.import_law(_make_create_req(effective_date=past_date))

    assert law.status == LawStatus.EFFECTIVE.value


@pytest.mark.asyncio
async def test_import_law_embedding_count_mismatch_raises() -> None:
    """embedding 数量与切分条款数不匹配 → AgentError。"""
    session = _mock_session()
    service = LegalLibraryService(session)

    # mock provider 返回数量不匹配
    bad_provider = AsyncMock()
    bad_provider.name = "mock"
    async def _bad_batch_embed(texts: list[str]) -> list[list[float]]:
        return [[0.1] * 1024 for _ in range(len(texts) - 1)]  # 少返回 1 个
    bad_provider.batch_embed = _bad_batch_embed

    with (
        patch.object(legal_library, "get_embedding_provider", lambda: bad_provider),
        pytest.raises(AgentError) as exc_info,
    ):
        await service.import_law(_make_create_req())

    assert "embedding" in str(exc_info.value).lower() or "不匹配" in str(exc_info.value)


@pytest.mark.asyncio
async def test_import_law_whitespace_raw_text_raises() -> None:
    """仅空白的 raw_text（通过 pydantic 校验但切分抛 AgentError）。"""
    session = _mock_session()
    service = LegalLibraryService(session)

    # 纯空白字符串能通过 pydantic min_length=1，但 split_law 会抛 AgentError
    req = _make_create_req(raw_text="   \n  \n  ")

    with pytest.raises(AgentError):
        await service.import_law(req)


@pytest.mark.asyncio
async def test_import_law_creates_one_law_and_multiple_clauses() -> None:
    """导入后：1 个 LegalDocument + N 个 LegalClause 被加入 session。"""
    session = _mock_session()
    service = LegalLibraryService(session)

    with _patch_provider(_mock_embedding_provider()):
        await service.import_law(_make_create_req())

    # add 调用次数 = 1 law + 3 clauses（SAMPLE_LAW_TEXT 切出 3 条）
    assert session.add.call_count == 1 + 3


@pytest.mark.asyncio
async def test_import_law_passes_keywords_to_orm() -> None:
    """keywords 字段透传到 LegalDocument ORM。"""
    session = _mock_session()
    service = LegalLibraryService(session)

    with _patch_provider(_mock_embedding_provider()):
        law = await service.import_law(_make_create_req())

    assert law.keywords == ["行政许可", "立法"]


# ============== check_time_validity ==============
@pytest.mark.asyncio
async def test_check_time_validity_not_yet_effective() -> None:
    """未生效（effective_date 在未来）。"""
    session = _mock_session()
    service = LegalLibraryService(session)

    future_date = date.today() + timedelta(days=30)
    mock_law = MagicMock()
    mock_law.id = uuid4()
    mock_law.law_name = "test"
    mock_law.status = LawStatus.DRAFT.value
    mock_law.effective_date = future_date
    mock_law.expire_date = None

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = mock_law
    session.execute.return_value = result_mock

    result = await service.check_time_validity(mock_law.id)

    assert result.is_effective is False
    assert "未生效" in (result.warning or "")
    assert result.days_to_expire is None


@pytest.mark.asyncio
async def test_check_time_validity_expired() -> None:
    """已过期（expire_date 在过去）。"""
    session = _mock_session()
    service = LegalLibraryService(session)

    past_date = date.today() - timedelta(days=30)
    mock_law = MagicMock()
    mock_law.id = uuid4()
    mock_law.law_name = "test"
    mock_law.status = LawStatus.EFFECTIVE.value
    mock_law.effective_date = date.today() - timedelta(days=100)
    mock_law.expire_date = past_date

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = mock_law
    session.execute.return_value = result_mock

    result = await service.check_time_validity(mock_law.id)

    assert result.is_effective is False
    assert "已过期" in (result.warning or "")


@pytest.mark.asyncio
async def test_check_time_validity_expiring_soon_warning() -> None:
    """即将过期（30 天内）。"""
    session = _mock_session()
    service = LegalLibraryService(session)

    expire_date = date.today() + timedelta(days=15)
    mock_law = MagicMock()
    mock_law.id = uuid4()
    mock_law.law_name = "test"
    mock_law.status = LawStatus.EFFECTIVE.value
    mock_law.effective_date = date.today() - timedelta(days=100)
    mock_law.expire_date = expire_date

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = mock_law
    session.execute.return_value = result_mock

    result = await service.check_time_validity(mock_law.id)

    assert result.is_effective is True
    assert "天后过期" in (result.warning or "")
    assert result.days_to_expire == 15


@pytest.mark.asyncio
async def test_check_time_validity_no_expiry_stays_effective() -> None:
    """无 expire_date → 永久有效，无警告。"""
    session = _mock_session()
    service = LegalLibraryService(session)

    mock_law = MagicMock()
    mock_law.id = uuid4()
    mock_law.law_name = "test"
    mock_law.status = LawStatus.EFFECTIVE.value
    mock_law.effective_date = date.today() - timedelta(days=100)
    mock_law.expire_date = None

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = mock_law
    session.execute.return_value = result_mock

    result = await service.check_time_validity(mock_law.id)

    assert result.is_effective is True
    assert result.warning is None
    assert result.days_to_expire is None


@pytest.mark.asyncio
async def test_check_time_validity_law_not_found() -> None:
    """法规不存在 → NotFoundError。"""
    session = _mock_session()
    service = LegalLibraryService(session)

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    session.execute.return_value = result_mock

    with pytest.raises(NotFoundError):
        await service.check_time_validity(uuid4())


# ============== update_law_status ==============
@pytest.mark.asyncio
async def test_update_law_status_changes_status() -> None:
    """状态变更。"""
    session = _mock_session()
    service = LegalLibraryService(session)

    mock_law = MagicMock()
    mock_law.id = uuid4()
    mock_law.law_name = "test"
    mock_law.status = LawStatus.EFFECTIVE.value
    mock_law.parent_law_id = None

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = mock_law
    session.execute.return_value = result_mock

    law = await service.update_law_status(mock_law.id, LawStatus.REPEALED)

    assert law.status == LawStatus.REPEALED.value
    assert session.flush.await_count == 1


@pytest.mark.asyncio
async def test_update_law_status_sets_parent_law_id() -> None:
    """指定 replaced_by_law_id → 建立 parent_law_id 修订链。"""
    session = _mock_session()
    service = LegalLibraryService(session)

    mock_law = MagicMock()
    mock_law.id = uuid4()
    mock_law.law_name = "old"
    mock_law.status = LawStatus.EFFECTIVE.value
    mock_law.parent_law_id = None

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = mock_law
    session.execute.return_value = result_mock

    replaced_by = uuid4()
    law = await service.update_law_status(
        mock_law.id, LawStatus.AMENDED, replaced_by_law_id=replaced_by
    )

    assert law.parent_law_id == replaced_by


@pytest.mark.asyncio
async def test_update_law_status_not_found() -> None:
    """法规不存在 → NotFoundError。"""
    session = _mock_session()
    service = LegalLibraryService(session)

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    session.execute.return_value = result_mock

    with pytest.raises(NotFoundError):
        await service.update_law_status(uuid4(), LawStatus.REPEALED)


# ============== get_law_with_clauses ==============
@pytest.mark.asyncio
async def test_get_law_with_clauses_returns_law() -> None:
    session = _mock_session()
    service = LegalLibraryService(session)

    mock_law = MagicMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = mock_law
    session.execute.return_value = result_mock

    result = await service.get_law_with_clauses(uuid4())
    assert result is mock_law


@pytest.mark.asyncio
async def test_get_law_with_clauses_not_found() -> None:
    session = _mock_session()
    service = LegalLibraryService(session)

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    session.execute.return_value = result_mock

    with pytest.raises(NotFoundError):
        await service.get_law_with_clauses(uuid4())


# ============== list_laws ==============
@pytest.mark.asyncio
async def test_list_laws_applies_filters_and_pagination() -> None:
    """list_laws 应用过滤条件并分页。"""
    session = _mock_session()
    service = LegalLibraryService(session)

    # mock 总数查询 + 列表查询 + clause 计数查询
    mock_law = MagicMock()
    mock_law.id = uuid4()
    mock_law.law_name = "test"
    mock_law.issuing_authority = "x"
    mock_law.publish_date = date.today()
    mock_law.effective_date = None
    mock_law.expire_date = None
    mock_law.law_type = "law"
    mock_law.law_level = "national"
    mock_law.version = "v1.0.0"
    mock_law.status = "effective"
    mock_law.keywords = []
    mock_law.created_at = date.today()

    list_result_mock = MagicMock()
    list_result_mock.scalars.return_value.all.return_value = [mock_law]
    count_result_mock = MagicMock()
    count_result_mock.scalar_one.return_value = 1
    cc_result_mock = MagicMock()
    cc_result_mock.all.return_value = [(mock_law.id, 5)]

    session.execute = AsyncMock(
        side_effect=[count_result_mock, list_result_mock, cc_result_mock]
    )

    items, total = await service.list_laws(
        law_type="law", law_level="national", status="effective",
        keyword="test", page=2, page_size=10,
    )

    assert total == 1
    assert len(items) == 1
    assert items[0].law_name == "test"
    assert items[0].clause_count == 5


@pytest.mark.asyncio
async def test_list_laws_no_keyword_filter() -> None:
    """无 keyword 时不应用 ilike 过滤。"""
    session = _mock_session()
    service = LegalLibraryService(session)

    list_result_mock = MagicMock()
    list_result_mock.scalars.return_value.all.return_value = []
    count_result_mock = MagicMock()
    count_result_mock.scalar_one.return_value = 0

    session.execute = AsyncMock(
        side_effect=[count_result_mock, list_result_mock]
    )

    items, total = await service.list_laws()

    assert total == 0
    assert items == []


# ============== batch_import ==============
@pytest.mark.asyncio
async def test_batch_import_tolerates_individual_failures() -> None:
    """单条失败不影响其他条目（容错）。"""
    session = _mock_session()
    service = LegalLibraryService(session)

    req_good = _make_create_req(law_name="good1")
    # 纯空白 raw_text 能通过 pydantic，但 split_law 会抛 AgentError
    req_bad = _make_create_req(law_name="bad", raw_text="   \n  \n  ")
    req_good2 = _make_create_req(law_name="good2")

    with _patch_provider(_mock_embedding_provider()):
        result = await service.batch_import([req_good, req_bad, req_good2])

    assert result.total == 3
    assert result.succeeded == 2
    assert result.failed == 1
    assert len(result.errors) == 1
    assert result.errors[0]["law_name"] == "bad"
    assert len(result.law_ids) == 2


@pytest.mark.asyncio
async def test_batch_import_all_success() -> None:
    """全部成功。"""
    session = _mock_session()
    service = LegalLibraryService(session)

    reqs = [_make_create_req(law_name=f"law_{i}") for i in range(3)]

    with _patch_provider(_mock_embedding_provider()):
        result = await service.batch_import(reqs)

    assert result.total == 3
    assert result.succeeded == 3
    assert result.failed == 0
    assert result.errors == []
    assert len(result.law_ids) == 3


@pytest.mark.asyncio
async def test_batch_import_empty_list() -> None:
    """空列表 → 0 成功 0 失败。"""
    session = _mock_session()
    service = LegalLibraryService(session)

    with _patch_provider(_mock_embedding_provider()):
        result = await service.batch_import([])

    assert result.total == 0
    assert result.succeeded == 0
    assert result.failed == 0
