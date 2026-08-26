"""API v1 路由聚合。"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    admin_user_feedback,
    audit,
    auth,
    documents,
    eval,
    feedback,
    legal,
    metrics,
    notifications,
    search,
    tasks,
    user_feedback,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(documents.router)
api_router.include_router(legal.router)
api_router.include_router(tasks.router)
api_router.include_router(eval.router)
api_router.include_router(feedback.router)
api_router.include_router(audit.router)
api_router.include_router(metrics.router)
api_router.include_router(notifications.router)
api_router.include_router(search.router)
api_router.include_router(user_feedback.router)
api_router.include_router(admin_user_feedback.router)

__all__ = ["api_router"]
