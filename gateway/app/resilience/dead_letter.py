"""死信队列：存储重试耗尽的失败任务，支持手动重放和排查。"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

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


class DeadLetterQueue:
    """内存死信队列（生产环境应持久化到 PostgreSQL）。"""

    def __init__(self, max_size: int = 10000):
        self._queue: list[DeadLetter] = []
        self._max_size = max_size

    def push(self, letter: DeadLetter) -> None:
        if len(self._queue) >= self._max_size:
            self._queue.pop(0)  # FIFO 淘汰最旧的
        self._queue.append(letter)

    def list(self, limit: int = 50, module_id: str | None = None) -> list[DeadLetter]:
        items = self._queue
        if module_id:
            items = [dl for dl in items if dl.module_id == module_id]
        return items[-limit:]

    def get(self, dlq_id: str) -> DeadLetter | None:
        for dl in self._queue:
            if dl.dlq_id == dlq_id:
                return dl
        return None

    def mark_replayed(self, dlq_id: str) -> bool:
        dl = self.get(dlq_id)
        if dl:
            dl.replayed = True
            return True
        return False

    def count(self, module_id: str | None = None) -> int:
        if module_id:
            return sum(1 for dl in self._queue if dl.module_id == module_id)
        return len(self._queue)

    def clear(self) -> int:
        count = len(self._queue)
        self._queue.clear()
        return count


# 全局 DLQ 实例
dlq = DeadLetterQueue()
