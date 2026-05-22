"""请求级中间件：访问日志 + 请求 ID + 简单限流挂点。"""
from __future__ import annotations

import time
import uuid

from fastapi import Request
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware


class AccessLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        request.state.request_id = rid
        t0 = time.perf_counter()
        with logger.contextualize(request_id=rid):
            try:
                resp = await call_next(request)
            except Exception:  # noqa: BLE001
                logger.exception("unhandled exception")
                raise
            cost = (time.perf_counter() - t0) * 1000
            logger.bind(
                method=request.method,
                path=request.url.path,
                status=resp.status_code,
                cost_ms=round(cost, 1),
            ).info("request done")
            resp.headers["x-request-id"] = rid
            return resp
