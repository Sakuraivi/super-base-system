from __future__ import annotations

from typing import TYPE_CHECKING

from superbase_sdk.schemas import IntentResult
from .mock_classifier import MockClassifier
from .cloud_classifier import CloudClassifier
from .complexity import ComplexityClassifier

if TYPE_CHECKING:
    from ..registry.store import ModuleRegistry


class IntentRouter:
    """意图路由器：根据配置选择 mock / cloud 模式，支持复杂度分级模型路由。"""

    def __init__(self, mode: str, registry: ModuleRegistry):
        self.mode = mode
        self._registry = registry
        self._mock = MockClassifier()
        self._cloud = CloudClassifier()

    async def route(self, user_message: str) -> IntentResult | None:
        if self.mode == "mock":
            result = self._mock.classify(user_message)
            if result:
                result.complexity = ComplexityClassifier.classify(user_message)
            return result

        # cloud 模式: 复杂度分级 + 模型路由
        complexity = ComplexityClassifier.classify(user_message)
        model = ComplexityClassifier.select_model(complexity)

        modules_info = [
            {
                "module_id": m.module_id,
                "name": m.name,
                "capabilities": [cap.model_dump() for cap in m.capabilities],
            }
            for m in self._registry.list_all()
        ]
        result = await self._cloud.classify(user_message, modules_info, model=model)
        if result:
            result.complexity = complexity
        return result
