import random
from superbase_sdk import ModuleServer, TaskRequest, TaskResponse

server = ModuleServer("weather", "0.1.0")

# Mock 天气数据（MVP 阶段不调用真实天气 API）
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
    return "北京"  # default


@server.execute
async def handle(req: TaskRequest) -> TaskResponse:
    city = _extract_city(req.query)
    weather = MOCK_WEATHER.get(city, {
        "temp": f"{random.randint(15, 35)}°C",
        "condition": random.choice(["晴", "多云", "阴", "小雨"]),
        "humidity": f"{random.randint(30, 90)}%",
        "wind": "微风",
    })

    summary = f"{city}天气：{weather['condition']}，{weather['temp']}，湿度{weather['humidity']}，{weather['wind']}"

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
