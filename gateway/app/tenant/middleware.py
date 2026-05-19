"""Tenant middleware: extracts tenant_id from request header and enforces rate limits."""
from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class RateLimiter:
    """Sliding window rate limiter per tenant.

    Tracks request timestamps per tenant and rejects requests that
    exceed the configured limit within the time window.
    """

    def __init__(self, max_requests: int = 60, window_seconds: int = 60):
        self._max_requests = max_requests
        self._window = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)

    def allow(self, tenant_id: str) -> bool:
        """Check if a request from this tenant is within rate limits."""
        now = time.monotonic()
        timestamps = self._requests[tenant_id]

        # Purge expired entries
        cutoff = now - self._window
        self._requests[tenant_id] = [t for t in timestamps if t > cutoff]
        timestamps = self._requests[tenant_id]

        if len(timestamps) >= self._max_requests:
            return False

        timestamps.append(now)
        return True

    def remaining(self, tenant_id: str) -> int:
        """Return remaining requests in current window."""
        now = time.monotonic()
        cutoff = now - self._window
        active = sum(1 for t in self._requests[tenant_id] if t > cutoff)
        return max(0, self._max_requests - active)


# 全局 rate limiter 实例
rate_limiter = RateLimiter()


class TenantMiddleware(BaseHTTPMiddleware):
    """Extract tenant_id from X-Tenant-ID header and enforce rate limits.

    - Sets request.state.tenant_id for downstream use
    - Returns 429 if tenant exceeds rate limit
    - Adds X-Tenant-ID and X-RateLimit-Remaining to response headers
    """

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        # 跳过健康检查和 metrics 端点
        path = request.url.path
        if path in ("/health", "/metrics"):
            return await call_next(request)

        # 提取 tenant_id
        tenant_id = request.headers.get("X-Tenant-ID", "default")
        request.state.tenant_id = tenant_id

        # Rate limiting
        if not rate_limiter.allow(tenant_id):
            logger.warning("[Tenant] Rate limit exceeded for tenant=%s", tenant_id)
            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "code": "RATE_LIMIT_EXCEEDED",
                        "message": f"Tenant '{tenant_id}' exceeded rate limit ({rate_limiter._max_requests} req/{rate_limiter._window}s)",
                    }
                },
            )

        response = await call_next(request)

        # 注入租户信息到响应头
        response.headers["X-Tenant-ID"] = tenant_id
        response.headers["X-RateLimit-Remaining"] = str(rate_limiter.remaining(tenant_id))
        return response
