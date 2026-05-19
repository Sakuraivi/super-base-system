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
from ..planner.condition_evaluator import ConditionEvaluator, ConditionEvalError
from ..dispatcher.http_dispatcher import HttpDispatcher
from ..registry.store import ModuleRegistry
from ..resilience.circuit_breaker import CircuitBreakerRegistry, CircuitState
from ..resilience.dead_letter import DeadLetter, dlq
from ..observability.metrics import DAG_NODE_STATUS, DAG_RETRY_COUNT

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

        return await self._run_loop(
            dag.plan_id, states, node_map, results, base_context, emit,
        )

    async def _run_loop(
        self,
        plan_id: str,
        states: dict[str, NodeState],
        node_map: dict[str, DAGNode],
        results: dict[str, Any],
        base_context: dict[str, Any],
        emit: ProgressCallback,
    ) -> dict[str, Any]:
        """核心拓扑排序执行循环，execute() 和 resume() 共用。"""
        remaining = set(node_map.keys())
        while remaining:
            ready = []
            for nid in remaining:
                node = node_map[nid]
                # 依赖检查：COMPLETED 或 AWAITING_HUMAN（门控节点在 remaining 外）
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

            # 记录节点状态指标
            for nid in ready:
                node = node_map[nid]
                DAG_NODE_STATUS.labels(
                    status=states[nid].status.value,
                    module_id=node.module_id or node.type.value,
                ).inc()

            # 条件分支跳过
            for nid in ready:
                node = node_map[nid]
                if node.type == NodeType.CONDITION and states[nid].status == NodeStatus.COMPLETED:
                    result_bool = results.get(nid, {}).get("condition", False)
                    await self._skip_branches(nid, node, result_bool, states, remaining, node_map, emit)

            # 人工门控检测：如果有人工门控节点进入 AWAITING_HUMAN，提前返回
            awaiting_gates = []
            for nid in ready:
                if states[nid].status == NodeStatus.AWAITING_HUMAN:
                    awaiting_gates.append(nid)
                    remaining.discard(nid)

            if awaiting_gates:
                return {
                    "plan_id": plan_id,
                    "status": "awaiting_human",
                    "awaiting_gates": awaiting_gates,
                    "node_states": {k: v.model_dump() for k, v in states.items()},
                    "results": results,
                    "_snapshot": {
                        "remaining": list(remaining),
                        "node_map": {nid: node_map[nid].model_dump() for nid in remaining},
                    },
                }

            for nid in ready:
                remaining.discard(nid)

        return {
            "plan_id": plan_id,
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
            await self._execute_condition(node_id, node, states, results, base_context, emit)
            return

        if node.type == NodeType.HUMAN_GATE:
            await self._start_human_gate(node_id, node, states, base_context, emit)
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
            await dlq.push(DeadLetter(
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
        DAG_RETRY_COUNT.observe(state.retries)
        breaker.record_failure()
        state.status = NodeStatus.FAILED
        state.error = last_error
        state.completed_at = datetime.now(timezone.utc).isoformat()

        await dlq.push(DeadLetter(
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

    async def _skip_branches(self, condition_nid, node, result, states, remaining, node_map, emit):
        """根据条件评估结果，跳过不需要执行的分支节点。"""
        skip_key = "false_branch" if result else "true_branch"
        keep_key = "true_branch" if result else "false_branch"
        skip_ids = set(node.config.get(skip_key, []))
        keep_ids = set(node.config.get(keep_key, []))
        to_skip = skip_ids - keep_ids

        for skip_nid in to_skip:
            if skip_nid in states and states[skip_nid].status == NodeStatus.PENDING:
                states[skip_nid].status = NodeStatus.SKIPPED
                states[skip_nid].error = f"Condition '{node.condition}' evaluated to {result}, branch skipped"
                states[skip_nid].completed_at = datetime.now(timezone.utc).isoformat()
                remaining.discard(skip_nid)
                await emit(skip_nid, "node_skipped", {
                    "node_id": skip_nid,
                    "reason": f"branch skipped by condition {condition_nid}",
                })

    async def _execute_condition(self, node_id, node, states, results, base_context, emit):
        state = states[node_id]
        state.status = NodeStatus.RUNNING
        state.started_at = datetime.now(timezone.utc).isoformat()
        await emit(node_id, "node_started", {"node_id": node_id, "type": "condition"})

        try:
            expr = node.condition
            if not expr:
                raise ConditionEvalError("Condition node has no expression")
            result = ConditionEvaluator.evaluate(expr, base_context, results)
        except (ConditionEvalError, Exception) as e:
            state.status = NodeStatus.FAILED
            state.error = f"Condition evaluation failed: {e}"
            state.completed_at = datetime.now(timezone.utc).isoformat()
            await emit(node_id, "node_error", {"node_id": node_id, "error": state.error})
            return

        state.status = NodeStatus.COMPLETED
        state.output = {"condition": expr, "evaluated": result}
        state.completed_at = datetime.now(timezone.utc).isoformat()
        results[node_id] = {"condition": result}
        await emit(node_id, "node_completed", {
            "node_id": node_id, "type": "condition", "result": result,
        })

    def get_circuit_state(self, module_id: str) -> str:
        return self._circuit_breakers.get_state(module_id).value

    def reset_circuit(self, module_id: str) -> None:
        self._circuit_breakers.reset(module_id)

    # ── 人工门控 ───────────────────────────────────────────────────

    async def _start_human_gate(self, node_id, node, states, base_context, emit):
        """遇到人工门控节点时，标记为 AWAITING_HUMAN 并等待回调。"""
        state = states[node_id]
        state.status = NodeStatus.AWAITING_HUMAN
        state.started_at = datetime.now(timezone.utc).isoformat()
        timeout = node.config.get("timeout_seconds", 300)
        default_action = node.config.get("default_action", "reject")

        await emit(node_id, "human_gate_waiting", {
            "node_id": node_id,
            "timeout_seconds": timeout,
            "default_action": default_action,
            "prompt": node.config.get("prompt", ""),
        })

    async def resume(
        self,
        session_id: str,
        gate_node_id: str,
        action: str,
        data: dict[str, Any] | None,
        session_manager: Any,
        on_progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        """人工门控回调后恢复 DAG 执行。"""
        snapshot = await session_manager.get_execution_snapshot(session_id)
        if not snapshot:
            return {"error": "No pending execution found"}

        # 重建执行状态
        states: dict[str, NodeState] = {
            k: NodeState(**v) for k, v in snapshot["states"].items()
        }
        results: dict[str, Any] = snapshot["results"]
        node_map: dict[str, DAGNode] = {
            k: DAGNode(**v) for k, v in snapshot["node_map"].items()
        }
        remaining = set(snapshot["remaining"])
        base_context = snapshot["base_context"]

        async def emit(node_id: str, event: str, data: dict[str, Any]):
            if on_progress:
                await on_progress(node_id, event, data)

        # 完成人工门控节点
        gate_state = states[gate_node_id]
        gate_state.status = NodeStatus.COMPLETED
        gate_state.output = {"action": action, "data": data or {}}
        gate_state.completed_at = datetime.now(timezone.utc).isoformat()
        results[gate_node_id] = gate_state.output

        await emit(gate_node_id, "human_gate_resumed", {
            "node_id": gate_node_id, "action": action,
        })

        # reject：跳过所有下游节点
        if action == "reject":
            to_skip = self._find_downstream(gate_node_id, node_map, remaining)
            for nid in to_skip:
                if states[nid].status == NodeStatus.PENDING:
                    states[nid].status = NodeStatus.SKIPPED
                    states[nid].error = f"Human gate {gate_node_id} rejected"
                    states[nid].completed_at = datetime.now(timezone.utc).isoformat()
                    remaining.discard(nid)
                    await emit(nid, "node_skipped", {
                        "node_id": nid,
                        "reason": f"rejected by human gate {gate_node_id}",
                    })

        # 继续拓扑排序执行剩余节点
        result = await self._run_loop(
            snapshot.get("plan_id", ""), states, node_map, results, base_context, emit,
        )

        # 清理快照
        await session_manager.clear_execution_snapshot(session_id)
        await session_manager.clear_pending_gate(session_id)

        return result

    def _find_downstream(
        self,
        gate_node_id: str,
        node_map: dict[str, DAGNode],
        remaining: set[str],
    ) -> list[str]:
        """BFS 找到门控节点所有下游依赖节点。"""
        downstream: list[str] = []
        queue = [gate_node_id]
        visited = {gate_node_id}

        while queue:
            current = queue.pop(0)
            for nid in remaining:
                if nid in visited:
                    continue
                node = node_map.get(nid)
                if node and current in node.depends_on:
                    downstream.append(nid)
                    visited.add(nid)
                    queue.append(nid)

        return downstream

    def _schedule_gate_timeout(
        self,
        session_id: str,
        gate_node_id: str,
        timeout_seconds: int,
        default_action: str,
        session_manager: Any,
    ) -> None:
        """安排人工门控超时自动执行（fire-and-forget）。"""
        async def _timeout_handler():
            await asyncio.sleep(timeout_seconds)
            gate = await session_manager.get_pending_gate(session_id)
            if gate and gate.get("node_id") == gate_node_id:
                await self.resume(
                    session_id, gate_node_id, default_action, None, session_manager,
                )

        asyncio.create_task(_timeout_handler())
