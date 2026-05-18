from __future__ import annotations

import time
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..intent.router import IntentRouter
from ..registry.store import ModuleRegistry
from ..dispatcher.http_dispatcher import HttpDispatcher
from ..session.manager import SessionManager

router = APIRouter()

# 模块级单例（在 main.py startup 之后由 app state 注入，或直接实例化）
_registry = ModuleRegistry()
_registry.load_from_directory()

_intent_router = IntentRouter(mode="mock", registry=_registry)
_dispatcher = HttpDispatcher()
_session_manager = SessionManager()


def configure_intent_mode(mode: str):
    """供启动时切换意图识别模式。"""
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
    modules_invoked: list[ModuleCallInfo] = Field(default_factory=list)
    usage: dict[str, int] = Field(default_factory=dict)


# ── Endpoints ─────────────────────────────────────────────────────

@router.post("/chat/completions", response_model=ChatResponse)
async def chat_completions(req: ChatRequest):
    request_id = str(uuid.uuid4())

    # 1. 会话管理
    session = _session_manager.get_or_create(req.session_id)
    session_id = session["session_id"]

    # 2. 意图识别
    intent = await _intent_router.route(req.message)
    if not intent:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "MODULE_NOT_FOUND",
                    "message": "无法匹配到合适的业务模块",
                    "trace_id": request_id,
                }
            },
        )

    # 3. 模块调度
    module = _registry.get(intent.module_id)
    if module is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "MODULE_NOT_FOUND",
                    "message": f"模块 {intent.module_id} 未注册",
                    "trace_id": request_id,
                }
            },
        )

    start = time.monotonic()
    task_request = {
        "task_id": request_id,
        "query": intent.query,
        "context": {**req.context, "session_id": session_id},
        "input_payload": {"entities": intent.entities},
        "config": {
            "timeout_seconds": module.timeout_seconds,
            "priority": req.options.get("priority", "normal"),
        },
    }

    result = await _dispatcher.dispatch(module, task_request)
    latency_ms = int((time.monotonic() - start) * 1000)

    # 4. 更新会话
    _session_manager.append_message(session_id, "user", req.message)
    _session_manager.append_message(session_id, "assistant", result.get("summary", ""))

    return ChatResponse(
        request_id=request_id,
        session_id=session_id,
        status=result.get("status", "completed"),
        message=result.get("summary", ""),
        modules_invoked=[
            ModuleCallInfo(
                module_id=intent.module_id,
                status=result.get("status", "completed"),
                latency_ms=latency_ms,
            )
        ],
        usage={
            "module_calls": 1,
            "latency_ms": latency_ms,
        },
    )


@router.get("/modules")
async def list_modules(intent: str | None = None):
    """列出已注册模块，可按 intent 过滤。"""
    modules = _registry.list_all()
    if intent:
        modules = [
            m for m in modules
            if any(cap.intent == intent for cap in m.capabilities)
        ]
    return {
        "modules": [
            {
                "module_id": m.module_id,
                "name": m.name,
                "version": m.version,
                "capabilities": [cap.model_dump() for cap in m.capabilities],
            }
            for m in modules
        ]
    }
