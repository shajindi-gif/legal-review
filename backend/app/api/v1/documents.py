"""文件上传 API - FR-001 ~ FR-010。

接口契约（来自架构文档第 10 节）：
POST /api/v1/documents/upload
Content-Type: multipart/form-data
Response: { task_id, trace_id, document_id, parse_status, status }

鉴权（Sprint 6.4）：
- 必须携带 Authorization: Bearer <access_token>
- submitter_id 直接取自 current_user.id（不再接受 header 透传）
- 上传前先消耗一次配额（Free 用户每日 3 次，Pro/Enterprise 不限）
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.nodes import trigger_doc_parse_background
from app.api.deps import get_audit_service, get_current_user, get_db, get_sandbox_dep
from app.core.constants import AuditAction, ParseStatus, TaskPriority, TaskStatus
from app.core.errors import AppError
from app.core.logging import get_logger
from app.models.document import Document
from app.models.task import ReviewTask
from app.models.user import User
from app.schemas.document import DocumentUploadResponse
from app.services.audit import AuditService
from app.services.quota_service import QuotaService
from app.services.sandbox import SandboxService

router = APIRouter(prefix="/documents", tags=["documents"])
logger = get_logger("api.documents")


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    responses={400: {"model": None}, 422: {"model": None}},
)
async def upload_document(
    file: UploadFile = File(..., description="送审文件，≤50MB，支持 docx/pdf/png/jpg/jpeg/txt"),
    title: str | None = Header(default=None, alias="X-Task-Title"),
    priority: str = Header(default=TaskPriority.NORMAL.value, alias="X-Priority"),
    current_user: User = Depends(get_current_user),
    sandbox: SandboxService = Depends(get_sandbox_dep),
    db: AsyncSession = Depends(get_db),
    audit: AuditService = Depends(get_audit_service),
) -> DocumentUploadResponse:
    """上传送审文件，自动创建任务并触发文件解析。

    鉴权：Bearer JWT（通过 ``get_current_user`` 注入当前用户）。

    请求头：
    - X-Task-Title: 任务标题（可选，缺省用文件名）
    - X-Priority: low|normal|high|urgent（默认 normal）

    配额：
    - Free 用户每日 3 次（超限返回 429 QuotaExceededError）
    - Pro/Enterprise 不限次数

    硬约束：
    - 文件大小 ≤ 50MB
    - 扩展名白名单
    - 路径防逃逸（沙箱隔离）
    - 任务级目录隔离
    - 全量审计日志
    - 送审人必须已挂靠组织
    """
    task_id = uuid4()
    trace_id = uuid4()

    quota = QuotaService(db)
    await quota.consume(current_user.id)

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="empty file")

    # 校验 + 沙箱写入（含大小/扩展名校验）
    storage_path_rel, file_type, file_size, file_hash = sandbox.save_upload(
        task_id=task_id, filename=file.filename or "unnamed", content=content
    )

    org_id = current_user.organization_id
    if org_id is None:
        raise AppError(
            http_status=400,
            code="USER_HAS_NO_ORG",
            message="当前用户未挂靠组织，请联系管理员完善资料",
        )

    # 创建任务（review_tasks）
    task = ReviewTask(
        id=task_id,
        trace_id=trace_id,
        title=title or (file.filename or "未命名任务"),
        submitter_id=current_user.id,
        submitter_org_id=org_id,
        status=TaskStatus.PARSING,
        current_node="doc_parse",
        priority=priority,
    )
    db.add(task)

    # 创建文件记录（documents）
    document = Document(
        task_id=task_id,
        original_name=file.filename or "unnamed",
        file_type=file_type,
        file_size=file_size,
        file_hash=file_hash,
        storage_path=storage_path_rel,
        mime_type=file.content_type,
        uploaded_by=current_user.id,
        parse_status=ParseStatus.PARSING,
    )
    db.add(document)

    # 审计日志
    await audit.log(
        action=AuditAction.UPLOAD,
        actor_id=current_user.id,
        actor_role=str(current_user.role),
        target_type="document",
        target_id=document.id,
        trace_id=trace_id,
        after_value={
            "task_id": str(task_id),
            "document_id": str(document.id),
            "original_name": document.original_name,
            "file_size": file_size,
            "file_hash": file_hash,
        },
    )

    await db.commit()

    logger.info(
        "document_uploaded",
        task_id=str(task_id),
        document_id=str(document.id),
        submitter_id=str(current_user.id),
        file_type=file_type,
        size=file_size,
    )

    # 触发完整审查工作流（后台异步，不阻塞上传响应）
    asyncio.create_task(
        trigger_doc_parse_background(task_id=task_id, document_id=document.id)
    )

    return DocumentUploadResponse(
        task_id=task_id,
        trace_id=trace_id,
        document_id=document.id,
        original_name=document.original_name,
        file_type=file_type,
        file_size=file_size,
        file_hash=file_hash,
        storage_path=storage_path_rel,
        parse_status=ParseStatus.PARSING.value,
        status=TaskStatus.PARSING.value,
    )
