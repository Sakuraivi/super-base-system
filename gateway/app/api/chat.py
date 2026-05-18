from __future__ import annotations

import json
import time
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..intent.router import IntentRouter
from ..intent.complexity import ComplexityClassifier
from ..planner.planner import TaskPlanner
from ..executor.dag_executor import DAGExecutor
from ..registry.store import ModuleRegistry
from ..dispatcher.http_dispatcher import HttpDispatcher
from ..session.manager import SessionManager
from ..transport.sse import SSEManager

router = APIRouter()

# 全局组件
_registry = ModuleRegistry()
_registry.load_from_directory()

_intent_router = IntentRouter(mode="mock", registry=_registry)
_dispatcher = HttpDispatcher()
_session_manager = SessionManager()
_task_planner = TaskPlanner()
_dag_executor = DAGExecutor(registry=_registry, dispatcher=_dispatcher)


def configure_intent_mode(mode: str):
    global _intent_router
    _intent_router = IntentRouter(mode=mode, registry=_registry)


# ── Request / Response ────────────────────────────────────────────

class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str
    context: dict[str, Any] = Field(default_factory=dict)
    options: dict[str, Any] = Field(default_factory=dict)


class ModuleCallInfo(BaseModel):
    module_id: str
    status: str
    latency_ms: int = 0


class ChatResponse(BaseModel):
    request_id: str
    session_id: str
    status: str
    message: str
    plan_id: str | None = None
    modules_invoked: list[ModuleCallInfo] = Field(default_factory=list)
    dag_result: dict[str, Any] | None = None
    usage: dict[str, int] = Field(default_factory=dict)


# ── Endpoints ─────────────────────────────────────────────────────

@router.post("/chat/completions")
async def chat_completions(req: ChatRequest):
    request_id = str(uuid.uuid4())
    stream = req.options.get("stream", False)

    # 1. 会话管理
    session = _session_manager.get_or_create(req.session_id)
    session_id = session["session_id"]

    # 2. 意图识别
    intent = await _intent_router.route(req.message)
    if not intent:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "MODULE_NOT_FOUND", "message": "无法匹配到合适的业务模块", "trace_id": request_id}},
        )

    # 3. DAG 编排
    complexity = intent.complexity
    dag = _task_planner.plan(
        intent_module_id=intent.module_id,
        query=req.message,
        complexity=complexity,
        entities=intent.entities,
    )

    # 4. 流式 / 非流式执行
    if stream:
        return StreamingResponse(
            _stream_execute(request_id, session_id, dag, req),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return await _execute_and_respond(request_id, session_id, dag, req)


async def _execute_and_respond(request_id, session_id, dag, req):
    start = time.monotonic()

    # 执行 DAG
    base_context = {
        "query": req.message,
        "session_id": session_id,
        "request_id": request_id,
        **req.context,
    }
    dag_result = await _dag_executor.execute(dag, base_context)
    latency_ms = int((time.monotonic() - start) * 1000)

    # 收集模块调用信息
    modules_invoked = []
    for node_id, state in dag_result.get("node_states", {}).items():
        if state.get("status") == "completed":
            module_id = "aggregator" if "aggregated" in state.get("output", {}) else state.get("output", {}).get("task_id", "").split("_")[0]
            modules_invoked.append(ModuleCallInfo(
                module_id=state.get("output", {}).get("context", {}).get("node_id", node_id),
                status="completed",
                latency_ms=latency_ms,
            ))

    # 聚合结果
    all_results = dag_result.get("results", {})
    summary_parts = []
    for nid, res in all_results.items():
        if isinstance(res, dict) and "summary" in res:
            summary_parts.append(res["summary"])
    message = " | ".join(summary_parts) if summary_parts else "执行完成"

    # 更新会话
    _session_manager.append_message(session_id, "user", req.message)
    _session_manager.append_message(session_id, "assistant", message)

    return ChatResponse(
        request_id=request_id,
        session_id=session_id,
        status="completed",
        message=message,
        plan_id=dag_result.get("plan_id"),
        modules_invoked=modules_invoked,
        dag_result=dag_result,
        usage={"latency_ms": latency_ms, "module_calls": len(all_results)},
    )


async def _stream_execute(request_id, session_id, dag, req):
    """SSE 流式执行 DAG。"""
    sse = SSEManager()

    yield sse.format_event("plan_created", {
        "plan_id": dag.plan_id,
        "type": dag.metadata.get("type", "single"),
        "nodes": [n.id for n in dag.nodes],
    })

    progress_events = []

    async def on_progress(node_id, event, data):
        progress_events.append((event, data))

    start = time.monotonic()
    base_context = {
        "query": req.message,
        "session_id": session_id,
        "request_id": request_id,
        **req.context,
    }

    dag_result = await _dag_executor.execute(dag, base_context, on_progress=on_progress)

    # 回放进度事件
    for event, data in progress_events:
        yield sse.format_event(event, data)

    # 最终结果
    all_results = dag_result.get("results", {})
    summary_parts = []
    for nid, res in all_results.items():
        if isinstance(res, dict) and "summary" in res:
            summary_parts.append(res["summary"])
    message = " | ".join(summary_parts) if summary_parts else "执行完成"
    latency_ms = int((time.monotonic() - start) * 1000)

    yield sse.format_event("completed", {
        "request_id": request_id,
        "status": "completed",
        "message": message,
        "latency_ms": latency_ms,
    })
    yield sse.format_done()

    _session_manager.append_message(session_id, "user", req.message)
    _session_manager.append_message(session_id, "assistant", message)


@router.get("/modules")
async def list_modules(intent: str | None = None):
    modules = _registry.list_all()
    if intent:
        modules = [m for m in modules if any(cap.intent == intent for cap in m.capabilities)]
    return {
        "modules": [
            {"module_id": m.module_id, "name": m.name, "version": m.version,
             "capabilities": [cap.model_dump() for cap in m.capabilities]}
            for m in modules
        ]
    }


@router.post("/plan/dag")
async def plan_dag(body: dict[str, Any]):
    """手动创建 DAG 执行计划。"""
    module_ids = body.get("module_ids", [])
    query = body.get("query", "")
    parallel = body.get("parallel", False)

    if not module_ids:
        raise HTTPException(status_code=400, detail="module_ids required")

    dag = _task_planner.plan_from_modules(module_ids, query, parallel)
    return dag.model_dump()


@router.post("/sessions/{session_id}/human-callback")
async def human_callback(session_id: str, body: dict[str, Any]):
    """人工介入回调。"""
    action = body.get("action", "approve")
    return {"status": "resumed", "message": f"已收到反馈: {action}，继续执行后续步骤"}
