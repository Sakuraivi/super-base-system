"""Integration tests for Human Gate (人工介入) lifecycle."""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from app.planner.dag import DAGDefinition, DAGNode, NodeType, NodeState, NodeStatus
from app.executor.dag_executor import DAGExecutor
from app.registry.store import ModuleRegistry
from app.dispatcher.http_dispatcher import HttpDispatcher
from app.session.manager import SessionManager


@pytest.fixture
def session_manager():
    return SessionManager()


@pytest.fixture
def mock_dispatcher():
    d = HttpDispatcher.__new__(HttpDispatcher)
    d.dispatch = AsyncMock(return_value={"status": "completed", "summary": "ok"})
    d.health_check = AsyncMock(return_value=True)
    return d


@pytest.fixture
def executor(mock_dispatcher):
    from superbase_sdk.schemas import ModuleManifest, ModuleCapability

    mock_module = ModuleManifest(
        module_id="echo",
        name="echo",
        version="0.1.0",
        description="mock",
        capabilities=[ModuleCapability(intent="echo", description="echo")],
        protocol="http",
        port=8001,
        timeout_seconds=10,
    )
    registry = ModuleRegistry.__new__(ModuleRegistry)
    registry._modules = {"echo": mock_module}
    registry.get = lambda mid: registry._modules.get(mid)
    return DAGExecutor(registry=registry, dispatcher=mock_dispatcher)


def make_gate_dag(timeout=300, default_action="reject"):
    gate = DAGNode(
        id="gate_1",
        type=NodeType.HUMAN_GATE,
        config={
            "timeout_seconds": timeout,
            "default_action": default_action,
            "prompt": "请审批",
        },
    )
    downstream = DAGNode(
        id="node_after",
        type=NodeType.MODULE,
        module_id="echo",
        depends_on=["gate_1"],
    )
    return DAGDefinition(nodes=[gate, downstream])


def make_parallel_gate_dag():
    gate = DAGNode(
        id="gate_1",
        type=NodeType.HUMAN_GATE,
        config={"timeout_seconds": 300, "default_action": "reject"},
    )
    independent = DAGNode(
        id="node_independent",
        type=NodeType.MODULE,
        module_id="echo",
    )
    downstream = DAGNode(
        id="node_after_gate",
        type=NodeType.MODULE,
        module_id="echo",
        depends_on=["gate_1"],
    )
    return DAGDefinition(nodes=[gate, independent, downstream])


# ── 基本 AWAITING_HUMAN 状态 ────────────────────────────────────

@pytest.mark.asyncio
async def test_gate_transitions_to_awaiting(executor):
    dag = make_gate_dag()
    events = []

    async def on_progress(node_id, event, data):
        events.append((event, data))

    result = await executor.execute(dag, {"query": "test"}, on_progress=on_progress)

    assert result["status"] == "awaiting_human"
    assert "gate_1" in result["awaiting_gates"]
    gate_state = result["node_states"]["gate_1"]
    assert gate_state["status"] == "awaiting_human"
    assert result["node_states"]["node_after"]["status"] == "pending"


@pytest.mark.asyncio
async def test_gate_emits_waiting_event(executor):
    dag = make_gate_dag()
    events = []

    async def on_progress(node_id, event, data):
        events.append((event, data))

    await executor.execute(dag, {"query": "test"}, on_progress=on_progress)

    waiting_events = [e for e in events if e[0] == "human_gate_waiting"]
    assert len(waiting_events) == 1
    assert waiting_events[0][1]["node_id"] == "gate_1"
    assert waiting_events[0][1]["prompt"] == "请审批"


@pytest.mark.asyncio
async def test_gate_snapshot_in_result(executor):
    dag = make_gate_dag()
    result = await executor.execute(dag, {"query": "test"})

    assert "_snapshot" in result
    assert "remaining" in result["_snapshot"]
    assert "node_map" in result["_snapshot"]


# ── 并行分支中独立节点继续执行 ──────────────────────────────────

@pytest.mark.asyncio
async def test_independent_branch_continues(executor, mock_dispatcher):
    dag = make_parallel_gate_dag()
    result = await executor.execute(dag, {"query": "test"})

    assert result["status"] == "awaiting_human"
    assert result["node_states"]["node_independent"]["status"] == "completed"


# ── Resume: approve ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_resume_approve(executor, session_manager):
    dag = make_gate_dag()
    result = await executor.execute(dag, {"query": "test"})

    await session_manager.get_or_create("sess_1")
    await session_manager.set_execution_snapshot("sess_1", {
        "plan_id": result["plan_id"],
        "states": result["node_states"],
        "results": result["results"],
        "node_map": result["_snapshot"]["node_map"],
        "remaining": result["_snapshot"]["remaining"],
        "base_context": {"query": "test"},
    })
    await session_manager.set_pending_gate("sess_1", {"node_id": "gate_1"})

    resume_result = await executor.resume(
        session_id="sess_1",
        gate_node_id="gate_1",
        action="approve",
        data=None,
        session_manager=session_manager,
    )

    assert "error" not in resume_result
    assert resume_result["node_states"]["gate_1"]["status"] == "completed"
    assert resume_result["node_states"]["gate_1"]["output"]["action"] == "approve"
    assert resume_result["node_states"]["node_after"]["status"] == "completed"


# ── Resume: reject ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_resume_reject_skips_downstream(executor, session_manager):
    dag = make_gate_dag()
    result = await executor.execute(dag, {"query": "test"})

    await session_manager.get_or_create("sess_1")
    await session_manager.set_execution_snapshot("sess_1", {
        "plan_id": result["plan_id"],
        "states": result["node_states"],
        "results": result["results"],
        "node_map": result["_snapshot"]["node_map"],
        "remaining": result["_snapshot"]["remaining"],
        "base_context": {"query": "test"},
    })
    await session_manager.set_pending_gate("sess_1", {"node_id": "gate_1"})

    resume_result = await executor.resume(
        session_id="sess_1",
        gate_node_id="gate_1",
        action="reject",
        data=None,
        session_manager=session_manager,
    )

    assert resume_result["node_states"]["gate_1"]["output"]["action"] == "reject"
    assert resume_result["node_states"]["node_after"]["status"] == "skipped"


# ── Resume: modify ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_resume_modify_with_data(executor, session_manager):
    dag = make_gate_dag()
    result = await executor.execute(dag, {"query": "test"})

    await session_manager.get_or_create("sess_1")
    await session_manager.set_execution_snapshot("sess_1", {
        "plan_id": result["plan_id"],
        "states": result["node_states"],
        "results": result["results"],
        "node_map": result["_snapshot"]["node_map"],
        "remaining": result["_snapshot"]["remaining"],
        "base_context": {"query": "test"},
    })
    await session_manager.set_pending_gate("sess_1", {"node_id": "gate_1"})

    modify_data = {"override": "new value"}
    resume_result = await executor.resume(
        session_id="sess_1",
        gate_node_id="gate_1",
        action="modify",
        data=modify_data,
        session_manager=session_manager,
    )

    assert resume_result["node_states"]["gate_1"]["output"]["data"] == modify_data
    assert resume_result["node_states"]["node_after"]["status"] == "completed"


# ── Resume: 无快照时返回错误 ────────────────────────────────────

@pytest.mark.asyncio
async def test_resume_no_snapshot(executor, session_manager):
    result = await executor.resume(
        session_id="nonexistent",
        gate_node_id="gate_1",
        action="approve",
        data=None,
        session_manager=session_manager,
    )
    assert "error" in result


# ── Resume 后快照被清理 ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_resume_clears_snapshot(executor, session_manager):
    dag = make_gate_dag()
    result = await executor.execute(dag, {"query": "test"})

    await session_manager.get_or_create("sess_1")
    await session_manager.set_execution_snapshot("sess_1", {
        "plan_id": result["plan_id"],
        "states": result["node_states"],
        "results": result["results"],
        "node_map": result["_snapshot"]["node_map"],
        "remaining": result["_snapshot"]["remaining"],
        "base_context": {"query": "test"},
    })
    await session_manager.set_pending_gate("sess_1", {"node_id": "gate_1"})

    await executor.resume(
        session_id="sess_1",
        gate_node_id="gate_1",
        action="approve",
        data=None,
        session_manager=session_manager,
    )

    assert await session_manager.get_execution_snapshot("sess_1") is None
    assert await session_manager.get_pending_gate("sess_1") is None
