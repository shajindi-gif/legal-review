"""健康检查 - 挂根路径，不进 /api/v1 前缀。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health", status_code=status.HTTP_200_OK)
async def health() -> dict:
    """存活探针（不查 DB）。"""
    settings = get_settings()
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
    }


@router.get("/ready", status_code=status.HTTP_200_OK)
async def readiness(db: AsyncSession = Depends(get_db)) -> dict:
    """就绪探针（含 DB 探活）。"""
    try:
        result = await db.execute(text("SELECT 1"))
        result.scalar()
        return {"status": "ready", "checks": {"db": "ok"}}
    except Exception as e:
        return {"status": "degraded", "checks": {"db": "fail", "error": str(e)}}
