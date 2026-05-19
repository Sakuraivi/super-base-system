"""Short-Term Memory: session-scoped conversation history with sliding window."""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class MemoryEntry(BaseModel):
    """Single memory entry in STM."""
    role: str
    content: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    token_count: int = 0


@runtime_checkable
class STMProtocol(Protocol):
    """Short-Term Memory async interface."""

    async def recall(self, session_id: str, current_query: str, max_turns: int = 10) -> list[dict]: ...
    async def store(self, session_id: str, role: str, content: str) -> None: ...
    async def get_summary(self, session_id: str) -> str | None: ...
    async def set_summary(self, session_id: str, summary: str) -> None: ...
    async def clear(self, session_id: str) -> None: ...


def estimate_tokens(text: str) -> int:
    """Estimate token count. Chinese: ~2 tokens/char, English: ~0.75 tokens/word."""
    chinese_chars = sum(1 for c in text if '一' <= c <= '鿿')
    other_chars = len(text) - chinese_chars
    return int(chinese_chars * 2 + other_chars * 0.4)


class InMemorySTM:
    """In-memory STM with sliding window and token budget."""

    def __init__(self, window_size: int = 10, max_tokens: int = 2000):
        self._store: dict[str, list[MemoryEntry]] = {}
        self._summaries: dict[str, str] = {}
        self._window_size = window_size
        self._max_tokens = max_tokens

    async def recall(self, session_id: str, current_query: str, max_turns: int = 10) -> list[dict]:
        """Retrieve recent conversation history within token budget."""
        entries = self._store.get(session_id, [])
        if not entries:
            return []

        # Sliding window: take last max_turns * 2 entries (user + assistant pairs)
        window = entries[-(max_turns * 2):]

        # Token budget: truncate from oldest if over budget
        result = []
        total_tokens = 0
        for entry in reversed(window):
            if total_tokens + entry.token_count > self._max_tokens:
                break
            result.append({
                "role": entry.role,
                "content": entry.content,
                "timestamp": entry.timestamp,
            })
            total_tokens += entry.token_count
        result.reverse()
        return result

    async def store(self, session_id: str, role: str, content: str) -> None:
        """Append a message to STM."""
        if session_id not in self._store:
            self._store[session_id] = []
        entry = MemoryEntry(
            role=role,
            content=content,
            token_count=estimate_tokens(content),
        )
        self._store[session_id].append(entry)

        # Trim to window size * 2 (keep recent entries)
        max_entries = self._window_size * 2
        if len(self._store[session_id]) > max_entries:
            self._store[session_id] = self._store[session_id][-max_entries:]

    async def get_summary(self, session_id: str) -> str | None:
        return self._summaries.get(session_id)

    async def set_summary(self, session_id: str, summary: str) -> None:
        self._summaries[session_id] = summary

    async def clear(self, session_id: str) -> None:
        self._store.pop(session_id, None)
        self._summaries.pop(session_id, None)
