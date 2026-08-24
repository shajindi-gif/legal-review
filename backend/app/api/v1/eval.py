"""评测系统 API - Sprint 5 / FR-029/031。

提供 Golden Dataset 导入/查询/删除 + EvalRun 触发/查询能力。
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_actor, get_audit_service, get_db
from app.core.constants import AuditAction, GoldenCategory
from app.schemas.eval import (
    EvalRunCreate,
    EvalRunRead,
    GoldenBatchImportRequest,
    GoldenBatchImportResponse,
    GoldenCaseCreate,
    GoldenCaseRead,
)
from app.services.audit import AuditService
from app.services.eval_runner import EvalRunner, GoldenDatasetService

router = APIRouter(prefix="/eval", tags=["eval"])


def get_golden_dataset_service(
    session: AsyncSession = Depends(get_db),
) -> GoldenDatasetService:
    return GoldenDatasetService(session)


def get_eval_runner(session: AsyncSession = Depends(get_db)) -> EvalRunner:
    return EvalRunner(session)


def _to_read(case) -> GoldenCaseRead:
    return GoldenCaseRead(
        id=case.id,
        case_name=case.case_name,
        category=case.category,
        input_file_path=case.input_file_path,
        expected_json=case.expected_json,
        expected_status=case.expected_status,
        notes=case.notes,
        created_at=case.created_at,
    )


def _to_run_read(run) -> EvalRunRead:
    return EvalRunRead(
        id=run.id,
        run_id=run.run_id,
        prompt_version=run.prompt_version,
        started_at=run.started_at,
        finished_at=run.finished_at,
        total_cases=run.total_cases,
        parse_acc=float(run.parse_acc) if run.parse_acc is not None else None,
        retrieval_acc=(
            float(run.retrieval_acc) if run.retrieval_acc is not None else None
        ),
        citation_acc=(
            float(run.citation_acc) if run.citation_acc is not None else None
        ),
        risk_kappa=float(run.risk_kappa) if run.risk_kappa is not None else None,
        report_complete=(
            float(run.report_complete) if run.report_complete is not None else None
        ),
        hallucination_rate=(
            float(run.hallucination_rate)
            if run.hallucination_rate is not None
            else None
        ),
        overall_pass=run.overall_pass,
        raw_result_path=run.raw_result_path,
    )


# ============== Golden Dataset ==============
@router.post(
    "/golden/cases",
    response_model=GoldenCaseRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_golden_case(
    req: GoldenCaseCreate,
    service: GoldenDatasetService = Depends(get_golden_dataset_service),
    audit: AuditService = Depends(get_audit_service),
    actor: dict = Depends(get_actor),
) -> GoldenCaseRead:
    """新增单条 Golden Case（FR-029 评测集管理）。"""
    cases = await service.batch_import([req])
    if cases.failed > 0:
        from app.core.errors import ValidationError

        raise ValidationError(f"导入失败：{cases.errors[0] if cases.errors else 'unknown'}")
    case = await service.list_cases()
    latest = case[0] if case else None
    if latest is None:
        from app.core.errors import AgentError

        raise AgentError("eval", "Golden Case 创建后未查到记录")

    await audit.log(
        action=AuditAction.CREATE,
        actor_id=actor.get("user_id"),
        actor_role=actor.get("role"),
        target_type="golden_case",
        target_id=latest.id,
        after_value={"case_name": latest.case_name, "category": latest.category},
        ip_address=actor.get("ip"),
    )
    return _to_read(latest)


@router.post(
    "/golden/import",
    response_model=GoldenBatchImportResponse,
    status_code=status.HTTP_200_OK,
)
async def batch_import_golden(
    req: GoldenBatchImportRequest,
    service: GoldenDatasetService = Depends(get_golden_dataset_service),
    audit: AuditService = Depends(get_audit_service),
    actor: dict = Depends(get_actor),
) -> GoldenBatchImportResponse:
    """批量导入 Golden Cases（容错）。"""
    result = await service.batch_import(req.cases)
    await audit.log(
        action=AuditAction.CREATE,
        actor_id=actor.get("user_id"),
        actor_role=actor.get("role"),
        target_type="golden_dataset",
        after_value={
            "total": result.total,
            "success": result.success,
            "failed": result.failed,
        },
        ip_address=actor.get("ip"),
    )
    return result


@router.get("/golden/cases", response_model=list[GoldenCaseRead])
async def list_golden_cases(
    category: GoldenCategory | None = Query(default=None),
    service: GoldenDatasetService = Depends(get_golden_dataset_service),
) -> list[GoldenCaseRead]:
    """查询 Golden Dataset（可选 category 过滤）。"""
    cases = await service.list_cases(
        category=category.value if category else None,
    )
    return [_to_read(c) for c in cases]


@router.get("/golden/cases/{case_id}", response_model=GoldenCaseRead)
async def get_golden_case(
    case_id: UUID,
    service: GoldenDatasetService = Depends(get_golden_dataset_service),
) -> GoldenCaseRead:
    """查询单条 Golden Case。"""
    case = await service.get_case(case_id)
    return _to_read(case)


@router.delete("/golden/cases/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_golden_case(
    case_id: UUID,
    service: GoldenDatasetService = Depends(get_golden_dataset_service),
    audit: AuditService = Depends(get_audit_service),
    actor: dict = Depends(get_actor),
) -> None:
    """删除单条 Golden Case。"""
    await service.delete_case(case_id)
    await audit.log(
        action=AuditAction.DELETE,
        actor_id=actor.get("user_id"),
        actor_role=actor.get("role"),
        target_type="golden_case",
        target_id=case_id,
        ip_address=actor.get("ip"),
    )


@router.get("/golden/count")
async def count_golden_cases(
    service: GoldenDatasetService = Depends(get_golden_dataset_service),
) -> dict:
    """统计 Golden Dataset 总数。"""
    return {"total": await service.count()}


# ============== EvalRun ==============
@router.post(
    "/runs",
    response_model=EvalRunRead,
    status_code=status.HTTP_201_CREATED,
)
async def trigger_eval_run(
    req: EvalRunCreate,
    runner: EvalRunner = Depends(get_eval_runner),
    audit: AuditService = Depends(get_audit_service),
    actor: dict = Depends(get_actor),
) -> EvalRunRead:
    """触发一次评测运行（FR-031 评测门控）。

    跑 Golden Dataset 计算 6 大指标 + overall_pass。
    """
    run = await runner.run(
        prompt_version=req.prompt_version,
        categories=req.categories,
        max_cases=req.max_cases,
    )
    await audit.log(
        action=AuditAction.REVIEW,
        actor_id=actor.get("user_id"),
        actor_role=actor.get("role"),
        target_type="eval_run",
        target_id=run.id,
        after_value={
            "run_id": str(run.run_id),
            "prompt_version": run.prompt_version,
            "overall_pass": run.overall_pass,
        },
        ip_address=actor.get("ip"),
    )
    return _to_run_read(run)


@router.get("/runs", response_model=list[EvalRunRead])
async def list_eval_runs(
    limit: int = Query(default=20, ge=1, le=100),
    runner: EvalRunner = Depends(get_eval_runner),
) -> list[EvalRunRead]:
    """评测运行历史列表。"""
    runs = await runner.list_runs(limit=limit)
    return [_to_run_read(r) for r in runs]


@router.get("/runs/{run_id}", response_model=EvalRunRead)
async def get_eval_run(
    run_id: UUID,
    runner: EvalRunner = Depends(get_eval_runner),
) -> EvalRunRead:
    """查询单次评测运行。"""
    run = await runner.get_run(run_id)
    return _to_run_read(run)
