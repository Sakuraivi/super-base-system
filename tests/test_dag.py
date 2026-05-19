"""Tests for DAG Planner and Executor."""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from app.planner.planner import TaskPlanner
from app.planner.dag import DAGDefinition, DAGNode, NodeType, NodeStatus
from superbase_sdk.schemas import Complexity
from app.executor.dag_executor import DAGExecutor
from app.registry.store import ModuleRegistry
from app.dispatcher.http_dispatcher import HttpDispatcher


@pytest.fixture
def planner():
    return TaskPlanner()


def test_single_plan(planner):
    dag = planner.plan("echo", "hello", Complexity.SINGLE)
    assert len(dag.nodes) == 1
    assert dag.nodes[0].module_id == "echo"
    assert dag.nodes[0].type == NodeType.MODULE


def test_pipeline_plan(planner):
    dag = planner.plan("echo", "hello", Complexity.PIPELINE)
    assert len(dag.nodes) == 2
    assert dag.nodes[1].depends_on == ["node_1"]


def test_dag_plan(planner):
    dag = planner.plan("echo", "hello", Complexity.DAG)
    assert len(dag.nodes) == 2


def test_manual_parallel_plan(planner):
    dag = planner.plan_from_modules(["echo", "weather", "code_review"], "test", parallel=True)
    # 3 modules + 1 aggregator
    assert len(dag.nodes) == 4
    # 并行：模块节点之间无依赖
    module_nodes = [n for n in dag.nodes if n.type == NodeType.MODULE]
    for n in module_nodes:
        assert n.depends_on == []


def test_manual_pipeline_plan(planner):
    dag = planner.plan_from_modules(["echo", "weather"], "test", parallel=False)
    assert len(dag.nodes) == 3
    assert dag.nodes[1].depends_on == ["node_1"]


# ── 条件分支测试 ─────────────────────────────────────────────────

@pytest.fixture
def mock_executor():
    """创建带 mock dispatcher 的 DAGExecutor。"""
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

    dispatcher = HttpDispatcher.__new__(HttpDispatcher)
    dispatcher.dispatch = AsyncMock(return_value={"status": "completed", "summary": "ok"})

    registry = ModuleRegistry.__new__(ModuleRegistry)
    registry._modules = {"echo": mock_module, "weather": mock_module}
    registry.get = lambda mid: registry._modules.get(mid)

    return DAGExecutor(registry=registry, dispatcher=dispatcher)


def _make_condition_dag(condition_expr, true_module="echo", false_module="weather"):
    """构建条件分支 DAG：条件 → true/false 两个模块 → 聚合器。"""
    cond = DAGNode(
        id="cond_1", type=NodeType.CONDITION, condition=condition_expr,
        config={"true_branch": ["node_true"], "false_branch": ["node_false"]},
    )
    node_true = DAGNode(
        id="node_true", type=NodeType.MODULE, module_id=true_module, depends_on=["cond_1"],
    )
    node_false = DAGNode(
        id="node_false", type=NodeType.MODULE, module_id=false_module, depends_on=["cond_1"],
    )
    agg = DAGNode(
        id="node_agg", type=NodeType.AGGREGATOR,
        depends_on=["node_true", "node_false"], input_from=["node_true", "node_false"],
    )
    return DAGDefinition(nodes=[cond, node_true, node_false, agg])


@pytest.mark.asyncio
async def test_condition_true_skips_false_branch(mock_executor):
    dag = _make_condition_dag("ctx.score > 80")
    result = await mock_executor.execute(dag, {"query": "test", "score": 90})

    assert result["node_states"]["cond_1"]["status"] == "completed"
    assert result["node_states"]["node_true"]["status"] == "completed"
    assert result["node_states"]["node_false"]["status"] == "skipped"


@pytest.mark.asyncio
async def test_condition_false_skips_true_branch(mock_executor):
    dag = _make_condition_dag("ctx.score > 80")
    result = await mock_executor.execute(dag, {"query": "test", "score": 50})

    assert result["node_states"]["cond_1"]["status"] == "completed"
    assert result["node_states"]["node_true"]["status"] == "skipped"
    assert result["node_states"]["node_false"]["status"] == "completed"


@pytest.mark.asyncio
async def test_condition_no_expression_fails(mock_executor):
    dag = _make_condition_dag(None)
    dag.nodes[0].condition = None
    result = await mock_executor.execute(dag, {"query": "test", "score": 50})

    assert result["node_states"]["cond_1"]["status"] == "failed"
    # 两个分支都应被跳过（依赖不满足）
    assert result["node_states"]["node_true"]["status"] == "skipped"
    assert result["node_states"]["node_false"]["status"] == "skipped"


@pytest.mark.asyncio
async def test_condition_downstream_of_skipped_also_skipped(mock_executor):
    """被跳过的分支，其下游依赖节点也应被跳过。"""
    cond = DAGNode(
        id="cond_1", type=NodeType.CONDITION, condition="ctx.go == True",
        config={"true_branch": ["node_true"], "false_branch": ["node_false"]},
    )
    node_true = DAGNode(
        id="node_true", type=NodeType.MODULE, module_id="echo", depends_on=["cond_1"],
    )
    node_false = DAGNode(
        id="node_false", type=NodeType.MODULE, module_id="echo", depends_on=["cond_1"],
    )
    # node_after 依赖被跳过的 node_false
    node_after = DAGNode(
        id="node_after", type=NodeType.MODULE, module_id="echo", depends_on=["node_false"],
    )
    dag = DAGDefinition(nodes=[cond, node_true, node_false, node_after])

    result = await mock_executor.execute(dag, {"query": "test", "go": True})

    assert result["node_states"]["node_true"]["status"] == "completed"
    assert result["node_states"]["node_false"]["status"] == "skipped"
    assert result["node_states"]["node_after"]["status"] == "skipped"


def test_plan_condition(planner):
    dag = planner.plan_condition(
        condition_expr="ctx.score > 80",
        true_module_id="echo",
        false_module_id="weather",
        query="test",
    )
    assert len(dag.nodes) == 4
    cond = [n for n in dag.nodes if n.type == NodeType.CONDITION][0]
    assert cond.condition == "ctx.score > 80"
    assert cond.config["true_branch"] == ["node_true"]
    assert cond.config["false_branch"] == ["node_false"]
