"""Weather module: LLM-powered weather analysis with natural language responses."""
from superbase_sdk import ModuleServer, TaskRequest, TaskResponse, LLMClient

server = ModuleServer("weather", "0.2.0")
llm = LLMClient()

# 保留 Mock 天气数据作为后备，LLM 用于生成分析和建议
MOCK_WEATHER = {
    "北京": {"temp": "22°C", "condition": "晴", "humidity": "35%", "wind": "北风 3级"},
    "上海": {"temp": "25°C", "condition": "多云", "humidity": "65%", "wind": "东南风 2级"},
    "深圳": {"temp": "28°C", "condition": "阵雨", "humidity": "80%", "wind": "南风 4级"},
    "东京": {"temp": "20°C", "condition": "阴", "humidity": "55%", "wind": "西风 2级"},
}


def _extract_city(query: str) -> str:
    for city in MOCK_WEATHER:
        if city in query:
            return city
    return "北京"


@server.execute
async def handle(req: TaskRequest) -> TaskResponse:
    city = _extract_city(req.query)
    weather = MOCK_WEATHER.get(city, {
        "temp": "22°C", "condition": "晴", "humidity": "50%", "wind": "微风",
    })

    # 用 LLM 生成自然语言天气分析和出行建议
    prompt = (
        f"你是一个天气助手。根据以下天气数据，用简洁友好的语言回答用户问题，"
        f"并给出出行或穿衣建议。\n\n"
        f"城市：{city}\n"
        f"天气数据：温度{weather['temp']}，{weather['condition']}，"
        f"湿度{weather['humidity']}，{weather['wind']}\n\n"
        f"用户问题：{req.query}\n\n"
        f"请直接回答，包含天气概况和实用建议。"
    )
    summary = await llm.complete(prompt, max_tokens=512, temperature=0.7)

    return TaskResponse(
        task_id=req.task_id,
        status="completed",
        summary=summary,
        output_payload={
            "city": city,
            "weather": weather,
        },
    )


app = server.app

if __name__ == "__main__":
    server.run(port=8002)
