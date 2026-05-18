from __future__ import annotations

import uuid
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class NodeType(str, Enum):
    MODULE = "module"          # 调用业务模块
    CONDITION = "condition"    # 条件分支
    AGGREGATOR = "aggregator"  # 结果聚合
    HUMAN_GATE = "human_gate"  # 人工介入


class NodeStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    AWAITING_HUMAN = "awaiting_human"
    SKIPPED = "skipped"


class DAGNode(BaseModel):
    id: str
    type: NodeType = NodeType.MODULE
    module_id: str | None = None
    depends_on: list[str] = Field(default_factory=list)
    input_from: list[str] = Field(default_factory=list)
    condition: str | None = None      # 条件节点的表达式
    config: dict[str, Any] = Field(default_factory=dict)


class DAGDefinition(BaseModel):
    """Task Planner 输出的 DAG 定义。"""
    plan_id: str = Field(default_factory=lambda: f"plan_{uuid.uuid4().hex[:12]}")
    nodes: list[DAGNode]
    metadata: dict[str, Any] = Field(default_factory=dict)


class NodeState(BaseModel):
    node_id: str
    status: NodeStatus = NodeStatus.PENDING
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    retries: int = 0
