"""Tests for DAG Planner and Executor."""
import pytest
import asyncio
from app.planner.planner import TaskPlanner
from app.planner.dag import NodeType
from superbase_sdk.schemas import Complexity


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
