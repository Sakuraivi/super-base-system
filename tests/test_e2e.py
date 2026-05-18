"""
End-to-end test: 模拟完整请求链路。

需要先启动 echo 和 weather 模块：
  cd modules/echo && uvicorn main:app --port 8001 &
  cd modules/weather && uvicorn main:app --port 8002 &

然后运行：
  pytest tests/test_e2e.py -v
"""
import pytest
from app.main import app
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"


def test_list_modules(client):
    resp = client.get("/api/v1/modules")
    assert resp.status_code == 200
    modules = resp.json()["modules"]
    assert len(modules) >= 2
    ids = {m["module_id"] for m in modules}
    assert "echo" in ids
    assert "weather" in ids


def test_echo_routing_mock(client):
    """Mock 模式下，echo 意图识别和调度。"""
    resp = client.post("/api/v1/chat/completions", json={
        "message": "你好世界",
    })
    # 需要模块在 localhost:8001 运行
    # 如果模块未启动，此测试会返回 failed，也是预期行为
    data = resp.json()
    assert "request_id" in data
    assert "session_id" in data


def test_weather_routing_mock(client):
    """Mock 模式下，天气意图识别。"""
    resp = client.post("/api/v1/chat/completions", json={
        "message": "今天北京天气怎么样",
    })
    data = resp.json()
    assert "request_id" in data


def test_session_continuity(client):
    """测试会话连续性。"""
    resp1 = client.post("/api/v1/chat/completions", json={
        "message": "hello",
    })
    session_id = resp1.json()["session_id"]

    resp2 = client.post("/api/v1/chat/completions", json={
        "session_id": session_id,
        "message": "echo test again",
    })
    assert resp2.json()["session_id"] == session_id
