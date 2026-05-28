"""FastAPI 入口 — 注册路由 / 中间件 / 生命周期 / 健康检查 / 指标。"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from app.api import (
    routes_auth,
    routes_chat,
    routes_health,
    routes_insight,
    routes_plan,
    routes_profile,
    routes_screening,
)
from app.config import get_settings
from app.core.db import close_db, init_db
from app.core.storage import ensure_bucket
from app.observability.logging import setup_logging
from app.observability.metrics import metrics_endpoint
from app.observability.middleware import AccessLogMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    s = get_settings()
    logger.info("starting {} env={}", s.app_name, s.app_env)
    try:
        await init_db()
    except Exception as e:  # noqa: BLE001
        logger.warning("DB init failed (will retry on demand): {}", e)
    try:
        ensure_bucket()
    except Exception as e:  # noqa: BLE001
        logger.warning("MinIO bucket ensure failed: {}", e)
    yield
    logger.info("shutting down")
    try:
        await close_db()
    except Exception:  # noqa: BLE001
        pass


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title=s.app_name,
        version="0.2.0",
        description="AI 营养健康多智能体协同平台",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(AccessLogMiddleware)

    app.include_router(routes_health.router, tags=["健康检查"])
    app.include_router(routes_auth.router, prefix="/api/auth", tags=["鉴权"])
    app.include_router(routes_chat.router, prefix="/api/chat", tags=["AI 营养师"])
    app.include_router(routes_screening.router, prefix="/api/screening", tags=["营养风险筛查"])
    app.include_router(routes_plan.router, prefix="/api/plan", tags=["个性化营养方案"])
    app.include_router(routes_insight.router, prefix="/api/insight", tags=["健康数据洞察"])
    app.include_router(routes_profile.router, prefix="/api/profile", tags=["用户画像"])

    if s.metrics_enabled:
        app.add_api_route(s.metrics_path, metrics_endpoint, methods=["GET"], include_in_schema=False)

    @app.exception_handler(Exception)
    async def _unhandled(request, exc):  # noqa: ANN001
        logger.exception("unhandled error")
        return JSONResponse(status_code=500, content={"type": "internal_error", "detail": str(exc)})

    return app


app = create_app()
