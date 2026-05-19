from __future__ import annotations

import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import Response

from .api.chat import router as chat_router
from .registry.store import ModuleRegistry
from .db.engine import init_db, is_pg_available
from .observability.tracing import init_tracing
from .observability.metrics import (
    REQUEST_COUNT, REQUEST_DURATION,
    get_metrics_bytes, get_metrics_content_type,
)
from .tenant.middleware import TenantMiddleware

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Super Base Gateway",
    version="0.1.0",
    description="超级基座调度系统 - 调度层",
)

# 多租户中间件（TenantMiddleware 使用 BaseHTTPMiddleware，需在其他中间件之前注册）
app.add_middleware(TenantMiddleware)

# 全局 Module Registry（启动时从 manifest 文件加载）
registry = ModuleRegistry()


@app.on_event("startup")
async def startup():
    registry.load_from_directory()
    init_tracing()
    if is_pg_available():
        await init_db()
        logger.info("[Startup] PostgreSQL initialized")
    else:
        logger.warning("[Startup] No DATABASE_URL — running in-memory mode")


# ── 可观测性中间件 ──────────────────────────────────────────────

@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    start = time.monotonic()

    response = await call_next(request)

    duration = time.monotonic() - start
    path = request.url.path

    # 跳过 /metrics 自身的统计（避免噪声）
    if path != "/metrics":
        method = request.method
        status = str(response.status_code)
        REQUEST_COUNT.labels(method=method, path=path, status=status).inc()
        REQUEST_DURATION.labels(method=method, path=path).observe(duration)

        logger.info(
            '{"request_id":"%s","method":"%s","path":"%s","status":%s,"duration_ms":%.1f}',
            request_id, method, path, response.status_code, duration * 1000,
        )

    response.headers["X-Request-ID"] = request_id
    return response


# ── Prometheus /metrics 端点 ────────────────────────────────────

@app.get("/metrics")
async def metrics():
    return Response(
        content=get_metrics_bytes(),
        media_type=get_metrics_content_type(),
    )


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "registered_modules": [
            m.module_id for m in registry.list_all()
        ],
    }


app.include_router(chat_router, prefix="/api/v1")
