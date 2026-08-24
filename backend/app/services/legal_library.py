"""法规库服务 - 导入/切分/索引/时效管理。

职责：
1. import_law(): 单部法规导入 → 切分 → 生成 embedding → 入库
2. batch_import(): 批量导入（容错）
3. check_time_validity(): 法规时效性检查（自动标记失效/即将失效）
4. update_law_status(): 法规状态变更（被修订/废止）
5. get_law_with_clauses(): 查询法规及条款
6. list_laws(): 法规列表

硬约束：
- 法规版本化：相同 law_name 不同 version 共存
- 法规修订：parent_law_id 链指向被修订法规
- 切分原子化：每条独立入库，含 embedding
- 全部操作走审计
"""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import LawStatus
from app.core.errors import AgentError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.legal import LegalClause, LegalDocument
from app.schemas.legal import (
    LawTimeValidity,
    LegalDocumentCreate,
    LegalDocumentRead,
    LegalLibraryImportResponse,
)
from app.tools.embedding import get_embedding_provider
from app.tools.legal_splitter import split_law

logger = get_logger("services.legal_library")


class LegalLibraryService:
    """法规库服务。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ============== 导入 ==============
    async def import_law(self, req: LegalDocumentCreate) -> LegalDocument:
        """导入单部法规：切分 + embedding + 入库。

        Returns:
            LegalDocument ORM（含 clauses 关系）
        """
        # 1. 切分
        clauses_data = split_law(req.raw_text, law_name=req.law_name)
        if not clauses_data:
            raise ValidationError(f"切分失败：{req.law_name}")

        # 2. 生成 embedding（批量）
        provider = get_embedding_provider()
        clause_texts = [c["content"] for c in clauses_data]
        try:
            embeddings = await provider.batch_embed(clause_texts)
        except AgentError:
            raise
        except Exception as e:
            raise AgentError("legal_retrieve", f"embedding 失败: {e}") from e

        if len(embeddings) != len(clauses_data):
            raise AgentError(
                "legal_retrieve",
                f"embedding 数量不匹配: {len(embeddings)} != {len(clauses_data)}",
            )

        # 3. 创建法规
        law = LegalDocument(
            law_name=req.law_name,
            issuing_authority=req.issuing_authority,
            publish_date=req.publish_date,
            effective_date=req.effective_date,
            expire_date=req.expire_date,
            law_type=req.law_type.value if hasattr(req.law_type, "value") else req.law_type,
            law_level=(
                req.law_level.value if hasattr(req.law_level, "value") else req.law_level
            ),
            version=req.version,
            status=LawStatus.EFFECTIVE.value
            if not req.effective_date or req.effective_date <= date.today()
            else LawStatus.DRAFT.value,
            raw_text=req.raw_text,
            keywords=req.keywords,
        )
        self._session.add(law)
        await self._session.flush()  # 拿到 law.id

        # 4. 创建条款
        for clause_data, emb in zip(clauses_data, embeddings, strict=True):
            clause = LegalClause(
                law_id=law.id,
                chapter=clause_data["chapter"],
                section=clause_data["section"],
                article_no=clause_data["article_no"],
                article_title=clause_data["article_title"],
                content=clause_data["content"],
                keywords=clause_data["keywords"],
                embedding=emb,
            )
            self._session.add(clause)

        await self._session.flush()
        logger.info(
            "law_imported",
            law_id=str(law.id),
            law_name=law.law_name,
            clauses=len(clauses_data),
            embedding_provider=provider.name,
        )
        return law

    async def batch_import(
        self, reqs: list[LegalDocumentCreate]
    ) -> LegalLibraryImportResponse:
        """批量导入（容错：单条失败不影响其他）。"""
        succeeded = 0
        failed = 0
        errors: list[dict[str, Any]] = []
        law_ids: list[UUID] = []

        for i, req in enumerate(reqs):
            try:
                law = await self.import_law(req)
                law_ids.append(law.id)
                succeeded += 1
            except Exception as e:
                failed += 1
                errors.append({
                    "index": i,
                    "law_name": req.law_name,
                    "error": str(e),
                })
                logger.warning("batch_import_failed", index=i, law=req.law_name, error=str(e))

        # 容错：失败条目回滚到 savepoint，整体不回滚
        await self._session.commit()
        return LegalLibraryImportResponse(
            total=len(reqs),
            succeeded=succeeded,
            failed=failed,
            errors=errors,
            law_ids=law_ids,
        )

    # ============== 时效管理 ==============
    async def check_time_validity(self, law_id: UUID) -> LawTimeValidity:
        """检查法规时效性，自动更新状态。"""
        result = await self._session.execute(
            select(LegalDocument).where(LegalDocument.id == law_id)
        )
        law = result.scalar_one_or_none()
        if law is None:
            raise NotFoundError("LegalDocument", str(law_id))

        today = date.today()
        is_effective = True
        warning: str | None = None
        days_to_expire: int | None = None

        # 还未生效
        if law.effective_date and law.effective_date > today:
            is_effective = False
            warning = f"未生效，生效日 {law.effective_date}"
        # 已过期
        elif law.expire_date and law.expire_date < today:
            is_effective = False
            warning = f"已过期，过期日 {law.expire_date}"
            if law.status == LawStatus.EFFECTIVE.value:
                await self._update_status(law, LawStatus.EXPIRED)
        # 即将过期（30 天内）
        elif law.expire_date:
            delta = (law.expire_date - today).days
            days_to_expire = delta
            if delta <= 30:
                warning = f"将于 {delta} 天后过期"

        return LawTimeValidity(
            law_id=law.id,
            law_name=law.law_name,
            status=law.status,
            is_effective=is_effective,
            expire_date=law.expire_date,
            days_to_expire=days_to_expire,
            warning=warning,
        )

    async def update_law_status(
        self,
        law_id: UUID,
        new_status: LawStatus,
        *,
        replaced_by_law_id: UUID | None = None,
    ) -> LegalDocument:
        """法规状态变更（被修订/废止）。

        若 replaced_by_law_id 指定，则建立 parent_law_id 修订链。
        """
        result = await self._session.execute(
            select(LegalDocument).where(LegalDocument.id == law_id)
        )
        law = result.scalar_one_or_none()
        if law is None:
            raise NotFoundError("LegalDocument", str(law_id))

        old_status = law.status
        law.status = new_status.value
        if replaced_by_law_id is not None:
            law.parent_law_id = replaced_by_law_id

        await self._session.flush()
        logger.info(
            "law_status_changed",
            law_id=str(law_id),
            old_status=old_status,
            new_status=new_status.value,
            replaced_by=str(replaced_by_law_id) if replaced_by_law_id else None,
        )
        return law

    async def _update_status(self, law: LegalDocument, new_status: LawStatus) -> None:
        law.status = new_status.value
        await self._session.flush()

    # ============== 查询 ==============
    async def get_law_with_clauses(self, law_id: UUID) -> LegalDocument:
        """查询法规及全部条款。"""
        result = await self._session.execute(
            select(LegalDocument).where(LegalDocument.id == law_id)
        )
        law = result.scalar_one_or_none()
        if law is None:
            raise NotFoundError("LegalDocument", str(law_id))
        return law

    async def list_laws(
        self,
        *,
        law_type: str | None = None,
        law_level: str | None = None,
        status: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[LegalDocumentRead], int]:
        """法规列表（含分页）。"""
        stmt = select(LegalDocument).where(LegalDocument.deleted_at.is_(None))
        if law_type:
            stmt = stmt.where(LegalDocument.law_type == law_type)
        if law_level:
            stmt = stmt.where(LegalDocument.law_level == law_level)
        if status:
            stmt = stmt.where(LegalDocument.status == status)
        if keyword:
            stmt = stmt.where(LegalDocument.law_name.ilike(f"%{keyword}%"))

        # 总数
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_result = await self._session.execute(count_stmt)
        total = total_result.scalar_one()

        # 分页
        stmt = stmt.order_by(LegalDocument.publish_date.desc())
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        result = await self._session.execute(stmt)
        laws = result.scalars().all()

        # 查 clause 数量
        clause_counts: dict[UUID, int] = {}
        if laws:
            law_ids = [law.id for law in laws]
            count_clauses = (
                select(LegalClause.law_id, func.count())
                .where(LegalClause.law_id.in_(law_ids))
                .group_by(LegalClause.law_id)
            )
            cc_result = await self._session.execute(count_clauses)
            clause_counts = {row[0]: row[1] for row in cc_result.all()}

        items = []
        for law in laws:
            item = LegalDocumentRead(
                id=law.id,
                law_name=law.law_name,
                issuing_authority=law.issuing_authority,
                publish_date=law.publish_date,
                effective_date=law.effective_date,
                expire_date=law.expire_date,
                law_type=law.law_type,
                law_level=law.law_level,
                version=law.version,
                status=law.status,
                keywords=law.keywords or [],
                clause_count=clause_counts.get(law.id, 0),
                created_at=law.created_at,
            )
            items.append(item)
        return items, total
