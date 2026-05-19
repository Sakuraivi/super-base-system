"""Redis-backed Short-Term Memory with sliding window and TTL."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import redis.asyncio as aioredis

from ..config import settings
from .stm import MemoryEntry, estimate_tokens

logger = logging.getLogger(__name__)


class RedisSTM:
    """STM backed by Redis.

    Storage:
        stm:{session_id}:messages — Redis List (LPUSH newest, LTRIM to window)
        stm:{session_id}:summary — Redis String (session summary)
        All keys have TTL (default 24h).
    """

    def __init__(
        self,
        redis_url: str | None = None,
        window_size: int = 10,
        max_tokens: int = 2000,
        ttl_seconds: int = 86400,
    ):
        self._redis_url = redis_url or settings.redis_url
        self._window_size = window_size
        self._max_tokens = max_tokens
        self._ttl = ttl_seconds
        self._client: aioredis.Redis | None = None

    async def _get_client(self) -> aioredis.Redis:
        if self._client is None:
            self._client = aioredis.from_url(
                self._redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
            )
        return self._client

    def _msg_key(self, session_id: str) -> str:
        return f"stm:{session_id}:messages"

    def _summary_key(self, session_id: str) -> str:
        return f"stm:{session_id}:summary"

    async def recall(self, session_id: str, current_query: str, max_turns: int = 10) -> list[dict]:
        client = await self._get_client()
        key = self._msg_key(session_id)

        # Get recent entries (LRANGE 0 to max_turns*2-1, newest first from LPUSH)
        raw_entries = await client.lrange(key, 0, max_turns * 2 - 1)
        if not raw_entries:
            return []

        # Parse and apply token budget
        result = []
        total_tokens = 0
        for raw in reversed(raw_entries):  # Reverse to chronological order
            entry = json.loads(raw)
            tokens = entry.get("token_count", 0)
            if total_tokens + tokens > self._max_tokens:
                break
            result.append({
                "role": entry["role"],
                "content": entry["content"],
                "timestamp": entry.get("timestamp", ""),
            })
            total_tokens += tokens

        # Refresh TTL on active session
        await client.expire(key, self._ttl)
        return result

    async def store(self, session_id: str, role: str, content: str) -> None:
        client = await self._get_client()
        key = self._msg_key(session_id)

        entry = {
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "token_count": estimate_tokens(content),
        }

        pipe = client.pipeline()
        pipe.lpush(key, json.dumps(entry, ensure_ascii=False))
        pipe.ltrim(key, 0, self._window_size * 2 - 1)
        pipe.expire(key, self._ttl)
        await pipe.execute()

    async def get_summary(self, session_id: str) -> str | None:
        client = await self._get_client()
        key = self._summary_key(session_id)
        summary = await client.get(key)
        if summary:
            await client.expire(key, self._ttl)
        return summary

    async def set_summary(self, session_id: str, summary: str) -> None:
        client = await self._get_client()
        key = self._summary_key(session_id)
        await client.set(key, summary, ex=self._ttl)

    async def clear(self, session_id: str) -> None:
        client = await self._get_client()
        await client.delete(self._msg_key(session_id), self._summary_key(session_id))

    async def close(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None
