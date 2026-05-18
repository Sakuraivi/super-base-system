from __future__ import annotations

import anthropic

from ..config import settings
from ..prompts.intent_prompt import build_intent_prompt, parse_intent_response
from superbase_sdk.schemas import IntentResult


class CloudClassifier:
    """通过 LLM API 进行意图分类，支持动态模型选择。"""

    def __init__(self):
        self._client = anthropic.Anthropic(
            base_url=settings.api_base_url,
            api_key=settings.api_key,
        )

    async def classify(
        self, text: str, modules: list[dict], model: str | None = None
    ) -> IntentResult | None:
        system_prompt = build_intent_prompt(text, modules)
        model = model or settings.model_name

        resp = self._client.messages.create(
            model=model,
            max_tokens=1024,
            system=system_prompt,
            messages=[{"role": "user", "content": text}],
        )

        # 提取文本内容（跳过 thinking block）
        text_content = ""
        for block in resp.content:
            if block.type == "text":
                text_content = block.text
                break

        if not text_content:
            return None

        return parse_intent_response(text_content)
