from __future__ import annotations

from typing import TYPE_CHECKING

from superbase_sdk.schemas import IntentResult
from .mock_classifier import MockClassifier
from .cloud_classifier import CloudClassifier

if TYPE_CHECKING:
    from ..registry.store import ModuleRegistry


class IntentRouter:
    """意图路由器：根据配置选择 mock / cloud 模式。"""

    def __init__(self, mode: str, registry: ModuleRegistry):
        self.mode = mode
        self._registry = registry
        self._mock = MockClassifier()
        self._cloud = CloudClassifier()

    async def route(self, user_message: str) -> IntentResult | None:
        if self.mode == "mock":
            return self._mock.classify(user_message)

        # cloud 模式: 从 registry 获取模块能力描述，传给 LLM
        modules_info = [
            {
                "module_id": m.module_id,
                "name": m.name,
                "capabilities": [cap.model_dump() for cap in m.capabilities],
            }
            for m in self._registry.list_all()
        ]
        return await self._cloud.classify(user_message, modules_info)
