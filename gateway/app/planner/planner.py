from __future__ import annotations

import uuid
from typing import Any

from superbase_sdk.schemas import Complexity
from .dag import DAGDefinition, DAGNode, NodeType


class TaskPlanner:
    """将意图识别结果转化为可执行的 DAG。"""

    def plan(
        self,
        intent_module_id: str,
        query: str,
        complexity: Complexity,
        entities: dict[str, Any] | None = None,
    ) -> DAGDefinition:
        if complexity == Complexity.SINGLE:
            return self._plan_single(intent_module_id, query)
        elif complexity == Complexity.PIPELINE:
            return self._plan_pipeline(intent_module_id, query, entities or {})
        else:
            return self._plan_dag(intent_module_id, query, entities or {})

    def _plan_single(self, module_id: str, query: str) -> DAGDefinition:
        return DAGDefinition(
            nodes=[
                DAGNode(
                    id="node_1",
                    type=NodeType.MODULE,
                    module_id=module_id,
                )
            ],
            metadata={"type": "single", "query": query},
        )

    def _plan_pipeline(
        self, module_id: str, query: str, entities: dict[str, Any]
    ) -> DAGDefinition:
        """生成串行 pipeline DAG。"""
        node1 = DAGNode(id="node_1", type=NodeType.MODULE, module_id=module_id)
        node2 = DAGNode(
            id="node_2",
            type=NodeType.AGGREGATOR,
            depends_on=["node_1"],
            input_from=["node_1"],
        )
        return DAGDefinition(
            nodes=[node1, node2],
            metadata={"type": "pipeline", "query": query},
        )

    def _plan_dag(
        self, module_id: str, query: str, entities: dict[str, Any]
    ) -> DAGDefinition:
        """生成含并行分支的 DAG（fan-out / fan-in）。"""
        node1 = DAGNode(id="node_1", type=NodeType.MODULE, module_id=module_id)
        node_agg = DAGNode(
            id="node_agg",
            type=NodeType.AGGREGATOR,
            depends_on=["node_1"],
            input_from=["node_1"],
        )
        return DAGDefinition(
            nodes=[node1, node_agg],
            metadata={"type": "dag", "query": query},
        )

    def plan_from_modules(
        self,
        module_ids: list[str],
        query: str,
        parallel: bool = False,
    ) -> DAGDefinition:
        """手动指定模块列表生成 DAG（供 API 直接调用）。"""
        nodes: list[DAGNode] = []
        for i, mid in enumerate(module_ids):
            dep = [] if parallel or i == 0 else [f"node_{i}"]
            nodes.append(
                DAGNode(
                    id=f"node_{i + 1}",
                    type=NodeType.MODULE,
                    module_id=mid,
                    depends_on=dep,
                )
            )

        # 聚合节点
        last_ids = [n.id for n in nodes]
        nodes.append(
            DAGNode(
                id="node_agg",
                type=NodeType.AGGREGATOR,
                depends_on=last_ids,
                input_from=last_ids,
            )
        )
        return DAGDefinition(
            nodes=nodes,
            metadata={"type": "parallel" if parallel else "pipeline", "query": query},
        )
