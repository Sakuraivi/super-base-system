"""E2E test with DAG execution - requires modules running on 8001/8002/8003."""
import time
import httpx
import json

client = httpx.Client(base_url="http://127.0.0.1:8000", timeout=30.0)

print("=== Phase 2 E2E Tests ===\n")

# 1. Health + module count
resp = client.get("/health")
data = resp.json()
print(f"[Health] modules={data['registered_modules']}")
assert len(data["registered_modules"]) >= 3, "Should have 3+ modules"
print()

# 2. Echo dispatch (single)
resp = client.post("/api/v1/chat/completions", json={"message": "hello"})
data = resp.json()
print(f"[Echo Single] status={data['status']}, msg={data['message'][:60]}")
assert data["status"] == "completed"
print()

# 3. Code review dispatch (single)
resp = client.post("/api/v1/chat/completions", json={"message": "帮我审查这段代码"})
data = resp.json()
print(f"[CodeReview] status={data['status']}, msg={data['message'][:80]}")
assert data["status"] == "completed"
assert "plan_id" in data
print()

# 4. Manual DAG (parallel)
resp = client.post("/api/v1/plan/dag", json={
    "module_ids": ["echo", "weather"],
    "query": "test parallel",
    "parallel": True,
})
dag = resp.json()
print(f"[DAG Plan] nodes={len(dag['nodes'])}, type={dag['metadata']['type']}")
assert len(dag["nodes"]) == 3  # 2 modules + 1 aggregator
print()

# 5. SSE streaming
print("[SSE Stream] testing...")
resp = client.post("/api/v1/chat/completions", json={
    "message": "echo streaming test",
    "options": {"stream": True},
}, timeout=30)
events = []
for line in resp.text.split("\n"):
    if line.startswith("event:"):
        events.append(line.split(":", 1)[1].strip())
print(f"  events received: {events}")
assert "plan_created" in events
assert "completed" in events or "done" in events
print()

# 6. Session continuity
resp1 = client.post("/api/v1/chat/completions", json={"message": "hello"})
sid = resp1.json()["session_id"]
resp2 = client.post("/api/v1/chat/completions", json={"session_id": sid, "message": "echo again"})
assert resp2.json()["session_id"] == sid
print(f"[Session] continuity OK")
print()

print("=== All Phase 2 E2E Tests Passed ===")
