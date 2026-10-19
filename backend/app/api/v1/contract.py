"""合同审查 API（PHASE 1-4）。

- POST /contract/reviews：上传合同文件（docx/pdf/txt）→ 解析 → 审查
- POST /contract/reviews/text：纯文本合同审查
- GET  /contract/reviews：当前租户合同审查列表
- GET  /contract/reviews/{id}：审查详情（findings + 对照修改视图 + 依据核验）
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.constants import ReviewStance
from app.core.errors import AppError, FileTooLargeError, FileTypeError, NotFoundError
from app.core.logging import get_logger
from app.schemas.contract import (
    ContractReviewListResponse,
    ContractReviewRead,
    ContractReviewRequest,
)
from app.services.contract_review import ContractReviewService
from app.services.core_auth_client import CorePrincipal
from app.tools import parsers

logger = get_logger("api.contract")

router = APIRouter(prefix="/contract", tags=["contract"])

_MAX_BYTES = 50 * 1024 * 1024  # 50MB
_ALLOWED_EXT = {"docx", "pdf", "txt"}


def get_contract_service(session: AsyncSession = Depends(get_db)) -> ContractReviewService:
    """合同审查服务依赖。"""
    return ContractReviewService(session)


def _parse_upload(file_name: str, content: bytes) -> dict:
    """把上传内容落临时文件并按扩展名解析（解析后即删）。"""
    ext = Path(file_name).suffix.lower().lstrip(".")
    if ext not in _ALLOWED_EXT:
        raise FileTypeError(f".{ext}", sorted(_ALLOWED_EXT))
    if len(content) > _MAX_BYTES:
        raise FileTooLargeError(
            len(content) / 1024 / 1024, _MAX_BYTES // 1024 // 1024
        )
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / f"contract.{ext}"
        path.write_bytes(content)
        parsed = parsers.parse(path, ext)
    if parsed.get("_needs_ocr"):
        raise AppError(
            http_status=422,
            code="OCR_REQUIRED",
            message="扫描版 PDF 需 OCR 识别，暂不支持，请上传可复制文本的文档",
        )
    return parsed


@router.post(
    "/reviews",
    response_model=ContractReviewRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_contract_review(
    file: UploadFile = File(..., description="合同文件，≤50MB，支持 docx/pdf/txt"),
    stance: ReviewStance = Form(default=ReviewStance.NEUTRAL, description="审查立场"),
    contract_type: str | None = Form(default=None, description="合同类型（可选）"),
    project_id: UUID | None = Form(default=None, description="所属项目（可选）"),
    service: ContractReviewService = Depends(get_contract_service),
    user: CorePrincipal = Depends(get_current_user),
) -> ContractReviewRead:
    """上传合同文件并执行审查（风险分级 + 对照修改视图 + 依据核验）。"""
    content = await file.read()
    if not content:
        raise AppError(http_status=400, code="empty_file", message="空文件")
    parsed = _parse_upload(file.filename or "contract.docx", content)
    return await service.review_document(
        parsed,
        original_name=file.filename,
        stance=stance,
        contract_type=contract_type,
        project_id=project_id,
        user=user,
    )


@router.post(
    "/reviews/text",
    response_model=ContractReviewRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_contract_review_text(
    req: ContractReviewRequest,
    service: ContractReviewService = Depends(get_contract_service),
    user: CorePrincipal = Depends(get_current_user),
) -> ContractReviewRead:
    """纯文本合同审查（快速通道，不走文件解析）。"""
    return await service.review_text(req, user=user)


@router.get("/reviews", response_model=ContractReviewListResponse)
async def list_contract_reviews(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    service: ContractReviewService = Depends(get_contract_service),
    user: CorePrincipal = Depends(get_current_user),
) -> ContractReviewListResponse:
    """当前租户下的合同审查列表。"""
    return await service.list_reviews(user=user, page=page, page_size=page_size)


@router.get("/reviews/{review_id}", response_model=ContractReviewRead)
async def get_contract_review(
    review_id: UUID,
    service: ContractReviewService = Depends(get_contract_service),
    user: CorePrincipal = Depends(get_current_user),
) -> ContractReviewRead:
    """合同审查详情。"""
    obj = await service.get_review(review_id, user=user)
    if obj is None:
        raise NotFoundError("ContractReview", str(review_id))
    return obj
