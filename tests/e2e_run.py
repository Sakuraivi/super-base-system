import time
import httpx
import json

time.sleep(2)

client = httpx.Client(base_url="http://127.0.0.1:8000", timeout=30.0)

print("=== E2E Test: Full Chain ===\n")

# Test 1: Health
resp = client.get("/health")
print(f"[Health] {resp.status_code}: {resp.json()}\n")

# Test 2: List modules
resp = client.get("/api/v1/modules")
modules = resp.json()["modules"]
print(f"[Modules] Registered: {[m['module_id'] for m in modules]}\n")

# Test 3: Echo dispatch
resp = client.post("/api/v1/chat/completions", json={"message": "你好世界"})
data = resp.json()
print(f"[Echo]   status={data['status']}, module={data['modules_invoked'][0]['module_id']}, msg={data['message']}")
print(f"         latency={data['usage']['latency_ms']}ms\n")

# Test 4: Weather dispatch
resp = client.post("/api/v1/chat/completions", json={"message": "今天北京天气怎么样"})
data = resp.json()
print(f"[Weather] status={data['status']}, module={data['modules_invoked'][0]['module_id']}, msg={data['message']}")
print(f"          latency={data['usage']['latency_ms']}ms\n")

# Test 5: No match
resp = client.post("/api/v1/chat/completions", json={"message": "帮我写一首诗"})
print(f"[NoMatch] status={resp.status_code}\n")

# Test 6: Session continuity
resp1 = client.post("/api/v1/chat/completions", json={"message": "hello"})
sid = resp1.json()["session_id"]
resp2 = client.post("/api/v1/chat/completions", json={"session_id": sid, "message": "echo test"})
print(f"[Session] same_session={resp2.json()['session_id'] == sid}\n")

print("=== All E2E Tests Complete ===")
