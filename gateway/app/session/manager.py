from __future__ import annotations

import uuid
from datetime import datetime, timezone


class SessionManager:
    """会话管理器（MVP: 内存存储，async 接口兼容 PG 实现）。"""

    def __init__(self):
        self._sessions: dict[str, dict] = {}

    async def get_or_create(self, session_id: str | None = None) -> dict:
        if session_id and session_id in self._sessions:
            return self._sessions[session_id]

        sid = session_id or f"sess_{uuid.uuid4().hex[:12]}"
        session = {
            "session_id": sid,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "messages": [],
        }
        self._sessions[sid] = session
        return session

    async def append_message(self, session_id: str, role: str, content: str) -> None:
        session = self._sessions.get(session_id)
        if session:
            session["messages"].append({
                "role": role,
                "content": content,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

    async def get_history(self, session_id: str) -> list[dict]:
        session = self._sessions.get(session_id)
        return session["messages"] if session else []

    # ── Human Gate 存储 ────────────────────────────────────────────

    async def set_pending_gate(self, session_id: str, gate_info: dict) -> None:
        session = self._sessions.get(session_id)
        if session:
            session["pending_human_gate"] = gate_info

    async def get_pending_gate(self, session_id: str) -> dict | None:
        session = self._sessions.get(session_id)
        return session.get("pending_human_gate") if session else None

    async def clear_pending_gate(self, session_id: str) -> None:
        session = self._sessions.get(session_id)
        if session:
            session.pop("pending_human_gate", None)

    # ── 执行快照存储（用于人工门控恢复） ──────────────────────────

    async def set_execution_snapshot(self, session_id: str, snapshot: dict) -> None:
        session = self._sessions.get(session_id)
        if session:
            session["execution_snapshot"] = snapshot

    async def get_execution_snapshot(self, session_id: str) -> dict | None:
        session = self._sessions.get(session_id)
        return session.get("execution_snapshot") if session else None

    async def clear_execution_snapshot(self, session_id: str) -> None:
        session = self._sessions.get(session_id)
        if session:
            session.pop("execution_snapshot", None)
