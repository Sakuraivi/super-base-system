"""死信队列：存储重试耗尽的失败任务，支持手动重放和排查。"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class DeadLetter(BaseModel):
    dlq_id: str = Field(default_factory=lambda: f"dlq_{uuid.uuid4().hex[:12]}")
    task_id: str
    module_id: str
    error: str
    retry_count: int = 0
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    replayed: bool = False


@runtime_checkable
class DLQProtocol(Protocol):
    """DLQ async interface shared by in-memory and PG implementations."""

    async def push(self, letter: DeadLetter) -> None: ...
    async def list(self, limit: int = 50, module_id: str | None = None) -> list[DeadLetter]: ...
    async def get(self, dlq_id: str) -> DeadLetter | None: ...
    async def mark_replayed(self, dlq_id: str) -> bool: ...
    async def count(self, module_id: str | None = None) -> int: ...
    async def clear(self) -> int: ...


class DeadLetterQueue:
    """内存死信队列（生产环境应持久化到 PostgreSQL）。"""

    def __init__(self, max_size: int = 10000):
        self._queue: list[DeadLetter] = []
        self._max_size = max_size

    async def push(self, letter: DeadLetter) -> None:
        if len(self._queue) >= self._max_size:
            self._queue.pop(0)
        self._queue.append(letter)

    async def list(self, limit: int = 50, module_id: str | None = None) -> list[DeadLetter]:
        items = self._queue
        if module_id:
            items = [dl for dl in items if dl.module_id == module_id]
        return items[-limit:]

    async def get(self, dlq_id: str) -> DeadLetter | None:
        for dl in self._queue:
            if dl.dlq_id == dlq_id:
                return dl
        return None

    async def mark_replayed(self, dlq_id: str) -> bool:
        dl = await self.get(dlq_id)
        if dl:
            dl.replayed = True
            return True
        return False

    async def count(self, module_id: str | None = None) -> int:
        if module_id:
            return sum(1 for dl in self._queue if dl.module_id == module_id)
        return len(self._queue)

    async def clear(self) -> int:
        count = len(self._queue)
        self._queue.clear()
        return count


# 全局 DLQ 实例（由 factory 在 startup 时决定使用 PG 或内存实现）
dlq: DLQProtocol = DeadLetterQueue()
