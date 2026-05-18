from __future__ import annotations

import asyncio
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
from ..resilience.circuit_breaker import CircuitBreakerRegistry, CircuitState
from ..resilience.dead_letter import DeadLetter, dlq

ProgressCallback = Callable[[str, str, dict[str, Any]], Awaitable[None]]


class DAGExecutor:
    """DAG 执行引擎：拓扑排序 + 熔断器 + 重试 + 死信队列 + 降级。"""

    def __init__(
        self,
        registry: ModuleRegistry,
        dispatcher: HttpDispatcher,
    ):
        self._registry = registry
        self._dispatcher = dispatcher
        self._max_retries = 2
        self._circuit_breakers = CircuitBreakerRegistry()

    async def execute(
        self,
        dag: DAGDefinition,
        base_context: dict[str, Any],
        on_progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        states: dict[str, NodeState] = {
            n.id: NodeState(node_id=n.id) for n in dag.nodes
        }
        node_map: dict[str, DAGNode] = {n.id: n for n in dag.nodes}
        results: dict[str, Any] = {}

        async def emit(node_id: str, event: str, data: dict[str, Any]):
            if on_progress:
                await on_progress(node_id, event, data)

        remaining = set(node_map.keys())
        while remaining:
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
                for nid in remaining:
                    if states[nid].status == NodeStatus.PENDING:
                        states[nid].status = NodeStatus.SKIPPED
                        states[nid].error = "Dependency not met"
                break

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

        module_id = node.module_id
        if not module_id:
            state.status = NodeStatus.FAILED
            state.error = "No module_id specified"
            return

        # 熔断器检查
        breaker = self._circuit_breakers.get_or_create(module_id)
        if not breaker.allow_request():
            state.status = NodeStatus.FAILED
            state.error = f"模块 {module_id} 已熔断（连续失败 {breaker.failure_count} 次），跳过调用"
            await emit(node_id, "node_error", {"node_id": node_id, "error": state.error, "circuit": "open"})
            # 进入 DLQ
            dlq.push(DeadLetter(
                task_id=node_id, module_id=module_id,
                error=state.error, payload=base_context,
            ))
            return

        state.status = NodeStatus.RUNNING
        state.started_at = datetime.now(timezone.utc).isoformat()
        await emit(node_id, "node_started", {"node_id": node_id, "module_id": module_id})

        module = self._registry.get(module_id)
        if module is None:
            state.status = NodeStatus.FAILED
            state.error = f"Module {module_id} not found in registry"
            await emit(node_id, "node_error", {"node_id": node_id, "error": state.error})
            return

        # 带重试的执行
        last_error = ""
        for attempt in range(self._max_retries + 1):
            try:
                task_request = {
                    "task_id": f"{node_id}_{attempt}",
                    "query": base_context.get("query", ""),
                    "context": {**base_context, "node_id": node_id},
                    "input_payload": {**base_context},
                    "config": {"timeout_seconds": module.timeout_seconds},
                }
                result = await self._dispatcher.dispatch(module, task_request)

                if result.get("status") == "completed":
                    # 成功：重置熔断器
                    breaker.record_success()
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
                    last_error = result.get("summary", "Module returned failed status")
            except Exception as e:
                last_error = str(e)

            state.retries = attempt + 1
            if attempt < self._max_retries:
                wait = min(2 ** attempt, 4)
                await emit(node_id, "node_retry", {
                    "node_id": node_id, "attempt": attempt + 1, "wait_seconds": wait,
                })
                await asyncio.sleep(wait)

        # 所有重试失败：记录熔断器 + DLQ
        breaker.record_failure()
        state.status = NodeStatus.FAILED
        state.error = last_error
        state.completed_at = datetime.now(timezone.utc).isoformat()

        dlq.push(DeadLetter(
            task_id=node_id, module_id=module_id,
            error=last_error, retry_count=self._max_retries,
            payload=base_context,
        ))

        await emit(node_id, "node_error", {
            "node_id": node_id, "error": last_error,
            "circuit_failures": breaker.failure_count,
        })

    async def _execute_aggregator(self, node_id, node, states, results, emit):
        state = states[node_id]
        state.status = NodeStatus.RUNNING
        aggregated = {}
        for src in node.input_from:
            if src in results:
                aggregated[src] = results[src]
        state.status = NodeStatus.COMPLETED
        state.output = {"aggregated": aggregated}
        state.completed_at = datetime.now(timezone.utc).isoformat()
        results[node_id] = aggregated
        await emit(node_id, "node_completed", {"node_id": node_id, "type": "aggregator"})

    async def _execute_condition(self, node_id, node, states, results, emit):
        state = states[node_id]
        state.status = NodeStatus.COMPLETED
        state.output = {"condition": node.condition, "evaluated": True}
        results[node_id] = {"condition": True}
        await emit(node_id, "node_completed", {"node_id": node_id, "type": "condition"})

    def get_circuit_state(self, module_id: str) -> str:
        return self._circuit_breakers.get_state(module_id).value

    def reset_circuit(self, module_id: str) -> None:
        self._circuit_breakers.reset(module_id)
