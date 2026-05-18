from __future__ import annotations

from superbase_sdk.schemas import Complexity


class ComplexityClassifier:
    """根据用户输入判断任务复杂度，用于模型路由和成本优化。"""

    # 简单: 单模块直连，意图明确
    SIMPLE_KEYWORDS = {"你好", "hello", "hi", "echo", "ping", "测试", "test", "天气", "weather"}

    # 复杂: 多步骤、DAG、条件分支
    COMPLEX_PATTERNS = [
        "然后", "接着", "同时", "并且", "首先", "最后",
        "and then", "also", "first", "finally", "in parallel",
        "分析.*并.*生成", "检查.*和.*修复",
    ]

    @classmethod
    def classify(cls, text: str) -> Complexity:
        text_lower = text.lower()

        # 检查是否包含复杂模式关键词
        for pattern in cls.COMPLEX_PATTERNS:
            if pattern in text_lower:
                return Complexity.DAG

        # 检查是否包含多个动作动词（暗示 pipeline）
        action_verbs = ["分析", "检查", "审查", "生成", "修复", "优化", "测试",
                        "analyze", "check", "review", "generate", "fix", "optimize", "test"]
        verb_count = sum(1 for v in action_verbs if v in text_lower)
        if verb_count >= 2:
            return Complexity.PIPELINE

        return Complexity.SINGLE

    @classmethod
    def select_model(cls, complexity: Complexity) -> str:
        """根据复杂度选择模型，平衡质量与成本。"""
        from ..config import settings
        model_map = {
            Complexity.SINGLE: settings.model_light,     # Haiku / 轻量模型
            Complexity.PIPELINE: settings.model_name,    # 标准模型
            Complexity.DAG: settings.model_name,         # 标准模型
        }
        return model_map.get(complexity, settings.model_name)
