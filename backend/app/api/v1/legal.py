"""法规库管理 API - FR-011 ~ FR-020。"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_actor, get_audit_service, get_db
from app.core.constants import AuditAction, LawLevel, LawStatus, LawType
from app.schemas.legal import (
    LawTimeValidity,
    LegalDocumentCreate,
    LegalDocumentRead,
    LegalLibraryImportRequest,
    LegalLibraryImportResponse,
    RAGSearchRequest,
    RAGSearchResponse,
)
from app.services.audit import AuditService
from app.services.legal_library import LegalLibraryService
from app.tools.rag import RAGSearchService

router = APIRouter(prefix="/legal", tags=["legal"])


def get_legal_library_service(
    session: AsyncSession = Depends(get_db),
) -> LegalLibraryService:
    return LegalLibraryService(session)


def get_rag_service(session: AsyncSession = Depends(get_db)) -> RAGSearchService:
    return RAGSearchService(session)


# ============== 导入 ==============
@router.post(
    "/import",
    response_model=LegalLibraryImportResponse,
    status_code=status.HTTP_200_OK,
)
async def import_laws(
    req: LegalLibraryImportRequest,
    service: LegalLibraryService = Depends(get_legal_library_service),
    audit: AuditService = Depends(get_audit_service),
    actor: dict = Depends(get_actor),
) -> LegalLibraryImportResponse:
    """批量导入法规（FR-012 法规导入）。

    每部法规自动切分 + embedding + 入库。
    单条失败不影响其他（容错）。
    """
    result = await service.batch_import(req.documents)

    await audit.log(
        action=AuditAction.CREATE,
        actor_id=actor.get("user_id"),
        actor_role=actor.get("role"),
        target_type="legal_library",
        after_value={
            "total": result.total,
            "succeeded": result.succeeded,
            "failed": result.failed,
        },
        ip_address=actor.get("ip"),
    )
    return result


@router.post(
    "/laws",
    response_model=LegalDocumentRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_law(
    req: LegalDocumentCreate,
    service: LegalLibraryService = Depends(get_legal_library_service),
    audit: AuditService = Depends(get_audit_service),
    actor: dict = Depends(get_actor),
) -> LegalDocumentRead:
    """导入单部法规（含切分与 embedding 索引）。"""
    law = await service.import_law(req)
    await service._session.commit()

    await audit.log(
        action=AuditAction.CREATE,
        actor_id=actor.get("user_id"),
        actor_role=actor.get("role"),
        target_type="legal_document",
        target_id=law.id,
        after_value={"law_name": law.law_name, "version": law.version},
        ip_address=actor.get("ip"),
    )

    # 转 Read（clause_count 单独查）
    clauses_count = len(law.clauses) if law.clauses else 0
    return LegalDocumentRead(
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
        clause_count=clauses_count,
        created_at=law.created_at,
    )


# ============== 查询 ==============
@router.get("/laws", response_model=list[LegalDocumentRead])
async def list_laws(
    law_type: LawType | None = Query(default=None),
    law_level: LawLevel | None = Query(default=None),
    status_filter: LawStatus | None = Query(default=None, alias="status"),
    keyword: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    service: LegalLibraryService = Depends(get_legal_library_service),
) -> list[LegalDocumentRead]:
    """法规列表（含分页 + 元数据过滤）。"""
    items, _ = await service.list_laws(
        law_type=law_type.value if law_type else None,
        law_level=law_level.value if law_level else None,
        status=status_filter.value if status_filter else None,
        keyword=keyword,
        page=page,
        page_size=page_size,
    )
    return items


@router.get("/laws/{law_id}", response_model=LegalDocumentRead)
async def get_law(
    law_id: UUID,
    service: LegalLibraryService = Depends(get_legal_library_service),
) -> LegalDocumentRead:
    """查询法规详情（含条款数）。"""
    from app.core.errors import NotFoundError

    law = await service.get_law_with_clauses(law_id)
    if law is None:
        raise NotFoundError("LegalDocument", str(law_id))
    return LegalDocumentRead(
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
        clause_count=len(law.clauses) if law.clauses else 0,
        created_at=law.created_at,
    )


# ============== 时效 ==============
@router.get("/laws/{law_id}/validity", response_model=LawTimeValidity)
async def check_validity(
    law_id: UUID,
    service: LegalLibraryService = Depends(get_legal_library_service),
) -> LawTimeValidity:
    """检查法规时效性（FR-016 法规时效性）。"""
    return await service.check_time_validity(law_id)


@router.post("/laws/{law_id}/status", response_model=LegalDocumentRead)
async def update_status(
    law_id: UUID,
    new_status: LawStatus,
    replaced_by_law_id: UUID | None = None,
    service: LegalLibraryService = Depends(get_legal_library_service),
    audit: AuditService = Depends(get_audit_service),
    actor: dict = Depends(get_actor),
) -> LegalDocumentRead:
    """法规状态变更（被修订/废止，FR-016）。

    若指定 replaced_by_law_id，则建立 parent_law_id 修订链。
    """
    law = await service.update_law_status(
        law_id, new_status, replaced_by_law_id=replaced_by_law_id
    )
    await service._session.commit()

    await audit.log(
        action=AuditAction.MODIFY,
        actor_id=actor.get("user_id"),
        actor_role=actor.get("role"),
        target_type="legal_document",
        target_id=law.id,
        after_value={
            "status": law.status,
            "replaced_by": str(replaced_by_law_id) if replaced_by_law_id else None,
        },
        ip_address=actor.get("ip"),
    )
    return LegalDocumentRead(
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
        clause_count=0,
        created_at=law.created_at,
    )


# ============== RAG 检索 ==============
@router.post("/search", response_model=RAGSearchResponse)
async def rag_search(
    req: RAGSearchRequest,
    rag: RAGSearchService = Depends(get_rag_service),
) -> RAGSearchResponse:
    """RAG 混合检索（FR-015 混合检索）。

    支持：
    - 关键词 + 向量混合检索
    - law_type/law_level/status 元数据过滤
    - Top-K 召回 + 加权融合
    """
    return await rag.search(req)
