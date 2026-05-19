"""Tests for observability: metrics, middleware, tracing."""
import pytest
from prometheus_client import CollectorRegistry
from app.observability.metrics import (
    REQUEST_COUNT, REQUEST_DURATION, DAG_DURATION,
    DAG_NODE_STATUS, MODULE_DURATION, MODULE_ERRORS,
    MEMORY_RECALL_DURATION, MEMORY_PROMOTE,
    INTENT_DURATION, DAG_RETRY_COUNT,
    get_metrics_bytes, get_metrics_content_type,
)


# ── Metrics Definitions ──────────────────────────────────────────

def test_metrics_exist():
    """All defined metrics should be importable."""
    assert REQUEST_COUNT is not None
    assert REQUEST_DURATION is not None
    assert DAG_DURATION is not None
    assert DAG_NODE_STATUS is not None
    assert MODULE_DURATION is not None
    assert MODULE_ERRORS is not None
    assert MEMORY_RECALL_DURATION is not None
    assert MEMORY_PROMOTE is not None
    assert INTENT_DURATION is not None
    assert DAG_RETRY_COUNT is not None


def test_metrics_bytes():
    """get_metrics_bytes should return bytes."""
    data = get_metrics_bytes()
    assert isinstance(data, bytes)
    assert len(data) > 0


def test_metrics_content_type():
    ct = get_metrics_content_type()
    assert "text/plain" in ct


# ── Counter Operations ───────────────────────────────────────────

def test_request_count_inc():
    """Counter should increment without error."""
    REQUEST_COUNT.labels(method="POST", path="/api/v1/chat/completions", status="200").inc()
    # No assertion needed - just verifying no exception


def test_module_errors_inc():
    MODULE_ERRORS.labels(module_id="echo", error_type="timeout").inc()


def test_dag_node_status_inc():
    DAG_NODE_STATUS.labels(status="completed", module_id="echo").inc()
    DAG_NODE_STATUS.labels(status="failed", module_id="weather").inc()


def test_memory_promote_inc():
    MEMORY_PROMOTE.inc()


# ── Histogram Operations ─────────────────────────────────────────

def test_dag_duration_observe():
    DAG_DURATION.observe(0.5)


def test_module_duration_observe():
    MODULE_DURATION.labels(module_id="echo").observe(0.1)


def test_intent_duration_observe():
    INTENT_DURATION.labels(mode="mock").observe(0.01)


def test_memory_recall_duration_observe():
    MEMORY_RECALL_DURATION.labels(source="total").observe(0.05)


def test_dag_retry_count_observe():
    DAG_RETRY_COUNT.observe(2)


# ── Tracing ──────────────────────────────────────────────────────

def test_tracing_import():
    from app.observability.tracing import get_tracer
    t = get_tracer("test")
    assert t is not None


def test_tracing_span():
    """Verify tracing module initializes and returns a functional tracer."""
    from app.observability.tracing import get_tracer
    import io
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor, ConsoleSpanExporter

    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter(out=io.StringIO())))
    trace.set_tracer_provider(provider)

    t = get_tracer("test")
    with t.start_as_current_span("test_span") as span:
        span.set_attribute("key", "value")
        assert span.is_recording()
