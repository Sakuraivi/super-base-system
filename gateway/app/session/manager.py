from __future__ import annotations

import uuid
from datetime import datetime, timezone


class SessionManager:
    """会话管理器（MVP: 内存存储）。"""

    def __init__(self):
        self._sessions: dict[str, dict] = {}

    def get_or_create(self, session_id: str | None = None) -> dict:
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

    def append_message(self, session_id: str, role: str, content: str) -> None:
        session = self._sessions.get(session_id)
        if session:
            session["messages"].append({
                "role": role,
                "content": content,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

    def get_history(self, session_id: str) -> list[dict]:
        session = self._sessions.get(session_id)
        return session["messages"] if session else []
