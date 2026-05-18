from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any, Callable, Awaitable

from ..planner.dag import (
    DAGDefinition,
    DAGNode,
    NodeState,
    NodeStatus,
    NodeType,
)
from ..dispatcher.http_dispatcher import HttpDispatcher
from ..registry.store import ModuleRegistry


# 进度回调类型
ProgressCallback = Callable[[str, str, dict[str, Any]], Awaitable[None]]


class DAGExecutor:
    """DAG 执行引擎：按拓扑序驱动节点执行，支持并行 barrier、超时、重试。"""

    def __init__(
        self,
        registry: ModuleRegistry,
        dispatcher: HttpDispatcher,
    ):
        self._registry = registry
        self._dispatcher = dispatcher
        self._max_retries = 2

    async def execute(
        self,
        dag: DAGDefinition,
        base_context: dict[str, Any],
        on_progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        """执行整个 DAG，返回所有节点输出的汇总。"""
        states: dict[str, NodeState] = {
            n.id: NodeState(node_id=n.id) for n in dag.nodes
        }
        node_map: dict[str, DAGNode] = {n.id: n for n in dag.nodes}
        results: dict[str, Any] = {}

        async def emit(node_id: str, event: str, data: dict[str, Any]):
            if on_progress:
                await on_progress(node_id, event, data)

        # 按层拓扑执行
        remaining = set(node_map.keys())
        while remaining:
            # 找出所有依赖已满足的节点
            ready = []
            for nid in remaining:
                node = node_map[nid]
                deps_met = all(
                    states[dep].status == NodeStatus.COMPLETED
                    for dep in node.depends_on
                )
                if deps_met and states[nid].status == NodeStatus.PENDING:
                    ready.append(nid)

            if not ready:
                # 没有可执行节点且还有 remaining → 死锁或全部失败
                for nid in remaining:
                    if states[nid].status == NodeStatus.PENDING:
                        states[nid].status = NodeStatus.SKIPPED
                        states[nid].error = "Dependency not met"
                break

            # 并行执行当前层所有就绪节点
            tasks = [
                self._execute_node(nid, node_map[nid], states, results, base_context, emit)
                for nid in ready
            ]
            await asyncio.gather(*tasks, return_exceptions=True)

            for nid in ready:
                remaining.discard(nid)

        return {
            "plan_id": dag.plan_id,
            "node_states": {k: v.model_dump() for k, v in states.items()},
            "results": results,
        }

    async def _execute_node(
        self,
        node_id: str,
        node: DAGNode,
        states: dict[str, NodeState],
        results: dict[str, Any],
        base_context: dict[str, Any],
        emit: ProgressCallback,
    ):
        state = states[node_id]

        if node.type == NodeType.AGGREGATOR:
            await self._execute_aggregator(node_id, node, states, results, emit)
            return

        if node.type == NodeType.CONDITION:
            await self._execute_condition(node_id, node, states, results, emit)
            return

        # MODULE 类型
        state.status = NodeStatus.RUNNING
        state.started_at = datetime.now(timezone.utc).isoformat()
        await emit(node_id, "node_started", {"node_id": node_id, "module_id": node.module_id})

        # 收集输入
        input_data = {**base_context}
        for src in node.input_from:
            if src in results:
                input_data[f"{src}_output"] = results[src]

        module = self._registry.get(node.module_id) if node.module_id else None
        if module is None:
            state.status = NodeStatus.FAILED
            state.error = f"Module {node.module_id} not found"
            await emit(node_id, "node_error", {"node_id": node_id, "error": state.error})
            return

        # 带重试的执行
        for attempt in range(self._max_retries + 1):
            try:
                task_request = {
                    "task_id": f"{node_id}_{attempt}",
                    "query": base_context.get("query", ""),
                    "context": {**base_context, "node_id": node_id},
                    "input_payload": input_data,
                    "config": {"timeout_seconds": module.timeout_seconds},
                }
                result = await self._dispatcher.dispatch(module, task_request)

                if result.get("status") == "completed":
                    state.status = NodeStatus.COMPLETED
                    state.output = result
                    state.completed_at = datetime.now(timezone.utc).isoformat()
                    results[node_id] = result
                    await emit(node_id, "node_completed", {
                        "node_id": node_id,
                        "output_summary": result.get("summary", ""),
                    })
                    return
                else:
                    state.error = result.get("summary", "Unknown error")
                    if attempt < self._max_retries:
                        state.retries = attempt + 1
                        await asyncio.sleep(min(2 ** attempt, 4))
                        continue
            except Exception as e:
                state.error = str(e)
                if attempt < self._max_retries:
                    state.retries = attempt + 1
                    await asyncio.sleep(min(2 ** attempt, 4))
                    continue

        state.status = NodeStatus.FAILED
        await emit(node_id, "node_error", {"node_id": node_id, "error": state.error})

    async def _execute_aggregator(
        self,
        node_id: str,
        node: DAGNode,
        states: dict[str, NodeState],
        results: dict[str, Any],
        emit: ProgressCallback,
    ):
        state = states[node_id]
        state.status = NodeStatus.RUNNING

        # 聚合所有上游输出
        aggregated = {}
        for src in node.input_from:
            if src in results:
                aggregated[src] = results[src]

        state.status = NodeStatus.COMPLETED
        state.output = {"aggregated": aggregated}
        state.completed_at = datetime.now(timezone.utc).isoformat()
        results[node_id] = aggregated
        await emit(node_id, "node_completed", {"node_id": node_id, "type": "aggregator"})

    async def _execute_condition(
        self,
        node_id: str,
        node: DAGNode,
        states: dict[str, NodeState],
        results: dict[str, Any],
        emit: ProgressCallback,
    ):
        state = states[node_id]
        state.status = NodeStatus.COMPLETED
        state.output = {"condition": node.condition, "evaluated": True}
        results[node_id] = {"condition": True}
        await emit(node_id, "node_completed", {"node_id": node_id, "type": "condition"})
