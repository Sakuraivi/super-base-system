"""Tests for multi-tenancy: tenant isolation and rate limiting."""
import pytest
from app.tenant.middleware import RateLimiter, TenantMiddleware


# ── RateLimiter ──────────────────────────────────────────────────

def test_rate_limiter_allows_within_limit():
    rl = RateLimiter(max_requests=5, window_seconds=60)
    for _ in range(5):
        assert rl.allow("tenant_a") is True


def test_rate_limiter_blocks_over_limit():
    rl = RateLimiter(max_requests=3, window_seconds=60)
    for _ in range(3):
        rl.allow("tenant_a")
    assert rl.allow("tenant_a") is False


def test_rate_limiter_tenant_isolation():
    rl = RateLimiter(max_requests=2, window_seconds=60)
    rl.allow("tenant_a")
    rl.allow("tenant_a")
    # tenant_a is at limit, tenant_b should still be allowed
    assert rl.allow("tenant_a") is False
    assert rl.allow("tenant_b") is True


def test_rate_limiter_remaining():
    rl = RateLimiter(max_requests=5, window_seconds=60)
    assert rl.remaining("t1") == 5
    rl.allow("t1")
    assert rl.remaining("t1") == 4
    rl.allow("t1")
    assert rl.remaining("t1") == 3


def test_rate_limiter_window_reset():
    """Rate limiter should reset after window expires."""
    rl = RateLimiter(max_requests=2, window_seconds=0.01)
    rl.allow("t1")
    rl.allow("t1")
    assert rl.allow("t1") is False

    import time
    time.sleep(0.02)
    assert rl.allow("t1") is True


# ── TenantMiddleware ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tenant_middleware_extracts_tenant_id():
    """Middleware should extract X-Tenant-ID header."""
    from starlette.applications import Starlette
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route
    from starlette.testclient import TestClient

    async def homepage(request):
        tenant_id = getattr(request.state, "tenant_id", "missing")
        return PlainTextResponse(tenant_id)

    app = Starlette(routes=[Route("/", homepage)])
    app.add_middleware(TenantMiddleware)

    client = TestClient(app)

    # With header
    resp = client.get("/", headers={"X-Tenant-ID": "acme"})
    assert resp.text == "acme"
    assert resp.headers["X-Tenant-ID"] == "acme"

    # Without header (default)
    resp = client.get("/")
    assert resp.text == "default"


@pytest.mark.asyncio
async def test_tenant_middleware_rate_limit():
    """Middleware should return 429 when rate limit exceeded."""
    from starlette.applications import Starlette
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route
    from starlette.testclient import TestClient
    from app.tenant import middleware as mw

    # Temporarily lower the rate limit for testing
    original_limiter = mw.rate_limiter
    mw.rate_limiter = RateLimiter(max_requests=2, window_seconds=60)

    async def homepage(request):
        return PlainTextResponse("ok")

    app = Starlette(routes=[Route("/", homepage)])
    app.add_middleware(TenantMiddleware)

    client = TestClient(app)

    # First 2 requests should succeed
    assert client.get("/", headers={"X-Tenant-ID": "limited"}).status_code == 200
    assert client.get("/", headers={"X-Tenant-ID": "limited"}).status_code == 200

    # Third should be 429
    resp = client.get("/", headers={"X-Tenant-ID": "limited"})
    assert resp.status_code == 429

    # Restore
    mw.rate_limiter = original_limiter


@pytest.mark.asyncio
async def test_tenant_middleware_skip_health():
    """Middleware should skip health and metrics endpoints."""
    from starlette.applications import Starlette
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route
    from starlette.testclient import TestClient

    async def health(request):
        return PlainTextResponse("healthy")

    app = Starlette(routes=[Route("/health", health)])
    app.add_middleware(TenantMiddleware)

    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    # Should NOT have X-Tenant-ID header (skipped by middleware)
    assert "X-Tenant-ID" not in resp.headers


# ── LTM Tenant Isolation ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_ltm_tenant_isolation():
    """LTM search should only return memories for the queried tenant."""
    from app.memory.ltm import InMemoryLTM
    from app.memory.embedding import MockEmbeddingClient

    embedding = MockEmbeddingClient(dimension=32)
    ltm = InMemoryLTM(embedding_client=embedding)

    await ltm.store("tenant A memory", {"session_id": "s1", "tenant_id": "tenant_a"})
    await ltm.store("tenant B memory", {"session_id": "s2", "tenant_id": "tenant_b"})

    # Search for tenant_a
    results_a = await ltm.search("memory", top_k=10, tenant_id="tenant_a")
    assert len(results_a) == 1
    assert "tenant A" in results_a[0]["content"]

    # Search for tenant_b
    results_b = await ltm.search("memory", top_k=10, tenant_id="tenant_b")
    assert len(results_b) == 1
    assert "tenant B" in results_b[0]["content"]

    # Search for nonexistent tenant
    results_c = await ltm.search("memory", top_k=10, tenant_id="tenant_c")
    assert len(results_c) == 0
