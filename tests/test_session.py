"""Unit tests for Session Manager."""
import pytest
from app.session.manager import SessionManager


@pytest.mark.asyncio
async def test_create_session():
    mgr = SessionManager()
    session = await mgr.get_or_create()
    assert session["session_id"].startswith("sess_")
    assert session["messages"] == []


@pytest.mark.asyncio
async def test_reuse_session():
    mgr = SessionManager()
    s1 = await mgr.get_or_create()
    s2 = await mgr.get_or_create(s1["session_id"])
    assert s1["session_id"] == s2["session_id"]


@pytest.mark.asyncio
async def test_append_message():
    mgr = SessionManager()
    session = await mgr.get_or_create()
    sid = session["session_id"]
    await mgr.append_message(sid, "user", "hello")
    await mgr.append_message(sid, "assistant", "hi there")

    history = await mgr.get_history(sid)
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[1]["content"] == "hi there"


@pytest.mark.asyncio
async def test_nonexistent_session():
    mgr = SessionManager()
    assert await mgr.get_history("nonexistent") == []


# ── Pending Gate 存储 ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pending_gate_set_get_clear():
    mgr = SessionManager()
    session = await mgr.get_or_create()
    sid = session["session_id"]

    assert await mgr.get_pending_gate(sid) is None

    gate_info = {"node_id": "gate_1", "session_id": sid}
    await mgr.set_pending_gate(sid, gate_info)
    assert await mgr.get_pending_gate(sid) == gate_info

    await mgr.clear_pending_gate(sid)
    assert await mgr.get_pending_gate(sid) is None


@pytest.mark.asyncio
async def test_pending_gate_nonexistent_session():
    mgr = SessionManager()
    assert await mgr.get_pending_gate("nonexistent") is None
    await mgr.set_pending_gate("nonexistent", {"node_id": "x"})
    await mgr.clear_pending_gate("nonexistent")


# ── Execution Snapshot 存储 ──────────────────────────────────────

@pytest.mark.asyncio
async def test_execution_snapshot_set_get_clear():
    mgr = SessionManager()
    session = await mgr.get_or_create()
    sid = session["session_id"]

    assert await mgr.get_execution_snapshot(sid) is None

    snapshot = {
        "plan_id": "plan_123",
        "states": {"node_1": {"status": "completed"}},
        "results": {"node_1": {"summary": "ok"}},
        "node_map": {},
        "remaining": [],
        "base_context": {"query": "test"},
    }
    await mgr.set_execution_snapshot(sid, snapshot)
    assert await mgr.get_execution_snapshot(sid) == snapshot

    await mgr.clear_execution_snapshot(sid)
    assert await mgr.get_execution_snapshot(sid) is None


@pytest.mark.asyncio
async def test_execution_snapshot_nonexistent_session():
    mgr = SessionManager()
    assert await mgr.get_execution_snapshot("nonexistent") is None
