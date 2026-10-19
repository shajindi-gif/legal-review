"""法律研究 API（PHASE 1-3）。

- POST /research/sessions：执行一次法律研究（结构化 8 段 + 引证核验）
- GET  /research/sessions：当前租户研究会话列表
- GET  /research/sessions/{id}：会话详情（引证含官方来源 URL）
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.errors import NotFoundError
from app.schemas.research import (
    ResearchRequest,
    ResearchSessionListResponse,
    ResearchSessionRead,
)
from app.services.core_auth_client import CorePrincipal
from app.services.legal_research import LegalResearchService

router = APIRouter(prefix="/research", tags=["research"])


def get_research_service(session: AsyncSession = Depends(get_db)) -> LegalResearchService:
    """法律研究服务依赖。"""
    return LegalResearchService(session)


@router.post(
    "/sessions",
    response_model=ResearchSessionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_research_session(
    req: ResearchRequest,
    service: LegalResearchService = Depends(get_research_service),
    user: CorePrincipal = Depends(get_current_user),
) -> ResearchSessionRead:
    """执行法律研究，返回结构化回答与逐条引证核验结果。"""
    return await service.create_session(req, user=user)


@router.get("/sessions", response_model=ResearchSessionListResponse)
async def list_research_sessions(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    service: LegalResearchService = Depends(get_research_service),
    user: CorePrincipal = Depends(get_current_user),
) -> ResearchSessionListResponse:
    """当前租户下的研究会话列表。"""
    return await service.list_sessions(user=user, page=page, page_size=page_size)


@router.get("/sessions/{session_id}", response_model=ResearchSessionRead)
async def get_research_session(
    session_id: UUID,
    service: LegalResearchService = Depends(get_research_service),
    user: CorePrincipal = Depends(get_current_user),
) -> ResearchSessionRead:
    """研究会话详情。"""
    obj = await service.get_session(session_id, user=user)
    if obj is None:
        raise NotFoundError("ResearchSession", str(session_id))
    return obj
