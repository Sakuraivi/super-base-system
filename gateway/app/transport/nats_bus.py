"""NATS JetStream 消息总线集成。

MVP 阶段为可选组件。如果 NATS 不可用，自动降级为同步 HTTP 调用。
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)


class NATSBus:
    """NATS JetStream 消息总线封装。"""

    def __init__(self, nats_url: str = "nats://localhost:4222"):
        self._url = nats_url
        self._nc = None
        self._js = None
        self._connected = False

    async def connect(self) -> bool:
        try:
            import nats
            self._nc = await nats.connect(self._url)
            self._js = self._nc.jetstream()
            self._connected = True
            logger.info(f"Connected to NATS at {self._url}")
            return True
        except Exception as e:
            logger.warning(f"NATS not available, falling back to sync: {e}")
            self._connected = False
            return False

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def publish_task(
        self,
        tenant_id: str,
        module_id: str,
        task_payload: dict[str, Any],
    ) -> bool:
        if not self._connected:
            return False

        subject = f"dispatch.{tenant_id}.{module_id}.task"
        data = json.dumps(task_payload, ensure_ascii=False).encode()
        await self._nc.publish(subject, data)
        return True

    async def subscribe_results(
        self,
        tenant_id: str,
        plan_id: str,
        callback: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        if not self._connected:
            return

        subject = f"result.{tenant_id}.{plan_id}.*"

        async def handler(msg):
            data = json.loads(msg.data.decode())
            await callback(data)
            await msg.ack()

        await self._js.subscribe(subject, cb=handler)

    async def publish_progress(
        self,
        tenant_id: str,
        plan_id: str,
        node_id: str,
        event_data: dict[str, Any],
    ) -> bool:
        if not self._connected:
            return False

        subject = f"progress.{tenant_id}.{plan_id}.{node_id}"
        data = json.dumps(event_data, ensure_ascii=False).encode()
        await self._nc.publish(subject, data)
        return True

    async def close(self):
        if self._nc:
            await self._nc.close()
            self._connected = False


# 全局 NATS 实例（惰性初始化）
_bus: NATSBus | None = None


async def get_nats_bus(nats_url: str = "nats://localhost:4222") -> NATSBus:
    global _bus
    if _bus is None:
        _bus = NATSBus(nats_url)
        await _bus.connect()
    return _bus
