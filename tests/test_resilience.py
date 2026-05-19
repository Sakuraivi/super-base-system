"""Tests for resilience mechanisms: circuit breaker, DLQ, fallback."""
import pytest
import time
from app.resilience.circuit_breaker import CircuitBreaker, CircuitState, CircuitBreakerRegistry
from app.resilience.dead_letter import DeadLetter, DeadLetterQueue


# ── Circuit Breaker ───────────────────────────────────────────────

def test_circuit_starts_closed():
    cb = CircuitBreaker()
    assert cb.state == CircuitState.CLOSED
    assert cb.allow_request() is True


def test_circuit_opens_after_threshold():
    cb = CircuitBreaker(failure_threshold=3)
    for _ in range(3):
        cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert cb.allow_request() is False


def test_circuit_half_open_after_timeout():
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.OPEN

    time.sleep(0.15)
    assert cb.allow_request() is True
    assert cb.state == CircuitState.HALF_OPEN


def test_circuit_resets_on_success():
    cb = CircuitBreaker(failure_threshold=2)
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.OPEN

    # Simulate recovery
    cb._last_failure_time = time.monotonic() - 100  # force timeout past
    cb.allow_request()  # moves to HALF_OPEN
    cb.record_success()
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 0


def test_circuit_reopens_on_failure_in_half_open():
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.01)
    cb.record_failure()
    cb.record_failure()
    time.sleep(0.02)
    cb.allow_request()  # HALF_OPEN
    cb.record_failure()
    assert cb.state == CircuitState.OPEN


def test_circuit_registry():
    reg = CircuitBreakerRegistry()
    cb1 = reg.get_or_create("module_a")
    cb2 = reg.get_or_create("module_a")
    assert cb1 is cb2  # same instance

    cb3 = reg.get_or_create("module_b")
    assert cb3 is not cb1


# ── Dead Letter Queue ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dlq_push_and_list():
    q = DeadLetterQueue(max_size=100)
    await q.push(DeadLetter(task_id="t1", module_id="m1", error="timeout"))
    await q.push(DeadLetter(task_id="t2", module_id="m2", error="crash"))

    assert await q.count() == 2
    assert len(await q.list()) == 2


@pytest.mark.asyncio
async def test_dlq_filter_by_module():
    q = DeadLetterQueue()
    await q.push(DeadLetter(task_id="t1", module_id="echo", error="e1"))
    await q.push(DeadLetter(task_id="t2", module_id="weather", error="e2"))
    await q.push(DeadLetter(task_id="t3", module_id="echo", error="e3"))

    assert await q.count(module_id="echo") == 2
    assert await q.count(module_id="weather") == 1


@pytest.mark.asyncio
async def test_dlq_max_size_eviction():
    q = DeadLetterQueue(max_size=3)
    for i in range(5):
        await q.push(DeadLetter(task_id=f"t{i}", module_id="m", error=f"e{i}"))

    assert await q.count() == 3
    items = await q.list()
    assert items[0].task_id == "t2"


@pytest.mark.asyncio
async def test_dlq_replay():
    q = DeadLetterQueue()
    await q.push(DeadLetter(task_id="t1", module_id="m1", error="e1"))
    items = await q.list()
    dlq_id = items[0].dlq_id

    assert await q.mark_replayed(dlq_id) is True
    dl = await q.get(dlq_id)
    assert dl.replayed is True


@pytest.mark.asyncio
async def test_dlq_clear():
    q = DeadLetterQueue()
    await q.push(DeadLetter(task_id="t1", module_id="m1", error="e1"))
    assert await q.clear() == 1
    assert await q.count() == 0
