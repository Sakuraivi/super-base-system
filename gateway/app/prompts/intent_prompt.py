from __future__ import annotations

from ..config import settings
from superbase_sdk.schemas import IntentResult


def build_intent_prompt(user_message: str, modules: list[dict]) -> str:
    """构建意图识别 system prompt。"""
    module_descriptions = []
    for m in modules:
        caps = []
        for cap in m.get("capabilities", []):
            kw = ", ".join(cap.get("keywords", []))
            caps.append(f"  - intent: {cap['intent']}, keywords: [{kw}]")
        module_descriptions.append(
            f"- module_id: {m['module_id']}\n  name: {m.get('name', '')}\n"
            + "\n".join(caps)
        )

    modules_text = "\n".join(module_descriptions) if module_descriptions else "(无可用模块)"

    return f"""你是一个意图识别路由器。根据用户的自然语言输入，判断应该调用哪个业务模块。

## 可用模块

{modules_text}

## 规则

1. 从用户输入中识别意图，匹配最合适的模块
2. 如果没有合适的模块，返回 module_id 为 "NONE"
3. 必须严格按 JSON 格式返回

## 输出格式

```json
{{
  "module_id": "最匹配的模块ID",
  "confidence": 0.0到1.0之间的置信度,
  "query": "传递给模块的处理后的查询",
  "entities": {{}},
  "reasoning": "简短说明选择理由"
}}
```

## 用户输入

{user_message}"""


def parse_intent_response(raw: str) -> IntentResult | None:
    """解析 LLM 返回的意图识别结果。"""
    import json
    import re

    # 尝试从 markdown code block 中提取 JSON
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    json_str = match.group(1) if match else raw

    # 尝试直接解析
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        # 最后尝试找到第一个 { 到最后一个 }
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(raw[start:end])
        else:
            return None

    module_id = data.get("module_id", "NONE")
    if module_id == "NONE":
        return None

    return IntentResult(
        module_id=module_id,
        confidence=float(data.get("confidence", 0.5)),
        query=data.get("query", ""),
        entities=data.get("entities", {}),
        reasoning=data.get("reasoning", ""),
    )
