"""FastAPI 应用入口。"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import api_router
from app.api.v1 import health as health_router
from app.core.config import get_settings
from app.core.errors import AppError, error_response
from app.core.logging import bind_trace_id, get_logger, setup_logging
from app.core.redis import close_redis
from app.db.session import dispose_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动/关闭钩子。"""
    setup_logging()
    logger = get_logger("app")
    logger.info("app_starting", app=get_settings().app_name)
    yield
    logger.info("app_stopping")
    await dispose_engine()
    await close_redis()


def create_app() -> FastAPI:
    """应用工厂。"""
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="行政规范性文件智能合法性审查 Agent 系统 API",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/api/v1/openapi.json",
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # trace_id 中间件
    @app.middleware("http")
    async def trace_id_middleware(request: Request, call_next):
        from uuid import uuid4

        trace_id = request.headers.get("X-Trace-Id") or str(uuid4())
        bind_trace_id(trace_id)
        response = await call_next(request)
        response.headers["X-Trace-Id"] = trace_id
        return response

    # 路由
    app.include_router(api_router)
    # health 路由挂根路径，不进 /api/v1 前缀
    app.include_router(health_router.router)

    # 全局异常处理
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        logger = get_logger("api")
        logger.warning(
            "app_error",
            code=exc.code,
            message=exc.message,
            path=request.url.path,
            trace_id=exc.trace_id,
        )
        return JSONResponse(status_code=exc.http_status, content=error_response(exc))

    return app


app = create_app()
