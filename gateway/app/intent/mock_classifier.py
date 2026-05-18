from __future__ import annotations

import re

from superbase_sdk.schemas import IntentResult, Complexity


class MockClassifier:
    """基于规则的 Mock 意图分类器，用于架构验证。"""

    # 规则: (正则模式, module_id, intent)
    RULES: list[tuple[str, str, str]] = [
        (r"(代码审查|code review|审查|review|安全检查|性能分析|安全扫描|漏洞|检查.*安全|检查.*PR|检查.*代码)", "code_review", "code_review"),
        (r"(天气|weather|温度|下雨|气温|forecast)", "weather", "weather_query"),
        (r"(你好|hello|hi|echo|ping|测试|test)", "echo", "echo"),
    ]

    def classify(self, text: str) -> IntentResult | None:
        for pattern, module_id, intent in self.RULES:
            if re.search(pattern, text, re.IGNORECASE):
                return IntentResult(
                    module_id=module_id,
                    confidence=0.95,
                    query=text,
                    complexity=Complexity.SINGLE,
                    reasoning=f"Mock: matched pattern '{pattern}'",
                )
        return None
