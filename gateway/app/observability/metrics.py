"""Prometheus metrics definitions."""
from __future__ import annotations

from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

# ── HTTP 请求级 ─────────────────────────────────────────────────

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
)

REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

# ── 意图识别 ────────────────────────────────────────────────────

INTENT_DURATION = Histogram(
    "intent_classify_duration_seconds",
    "Intent classification duration",
    ["mode"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5],
)

# ── DAG 执行 ────────────────────────────────────────────────────

DAG_DURATION = Histogram(
    "dag_execute_duration_seconds",
    "DAG execution duration",
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 5.0, 10.0],
)

DAG_NODE_STATUS = Counter(
    "dag_node_status_total",
    "DAG node status transitions",
    ["status", "module_id"],
)

DAG_RETRY_COUNT = Histogram(
    "dag_retry_count",
    "Retry attempts per node",
    buckets=[0, 1, 2, 3, 5],
)

# ── 模块调用 ────────────────────────────────────────────────────

MODULE_DURATION = Histogram(
    "module_dispatch_duration_seconds",
    "Module dispatch duration",
    ["module_id"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 5.0],
)

MODULE_ERRORS = Counter(
    "module_dispatch_errors_total",
    "Module dispatch errors",
    ["module_id", "error_type"],
)

# ── 记忆系统 ────────────────────────────────────────────────────

MEMORY_RECALL_DURATION = Histogram(
    "memory_recall_duration_seconds",
    "Memory recall duration",
    ["source"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5],
)

MEMORY_PROMOTE = Counter(
    "memory_promote_total",
    "Memory promotions to LTM",
)

# ── Prometheus /metrics 端点 ────────────────────────────────────


def get_metrics_bytes() -> bytes:
    """Generate Prometheus metrics payload."""
    return generate_latest()


def get_metrics_content_type() -> str:
    return CONTENT_TYPE_LATEST
