"""Unit tests for Short-Term Memory (STM)."""
import pytest
from app.memory.stm import InMemorySTM, MemoryEntry, estimate_tokens


# ── Token Estimation ─────────────────────────────────────────────

def test_estimate_tokens_chinese():
    assert estimate_tokens("你好世界") == 8  # 4 chars * 2


def test_estimate_tokens_english():
    tokens = estimate_tokens("hello world")
    assert 3 <= tokens <= 10  # ~11 chars * 0.4


def test_estimate_tokens_mixed():
    tokens = estimate_tokens("hello 你好")
    assert tokens > 0


def test_estimate_tokens_empty():
    assert estimate_tokens("") == 0


# ── InMemorySTM: Store and Recall ────────────────────────────────

@pytest.mark.asyncio
async def test_store_and_recall():
    stm = InMemorySTM(window_size=10, max_tokens=2000)
    await stm.store("sess_1", "user", "hello")
    await stm.store("sess_1", "assistant", "hi there")

    history = await stm.recall("sess_1", "next message")
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "hello"
    assert history[1]["role"] == "assistant"
    assert history[1]["content"] == "hi there"


@pytest.mark.asyncio
async def test_recall_empty_session():
    stm = InMemorySTM()
    history = await stm.recall("nonexistent", "query")
    assert history == []


# ── Sliding Window ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sliding_window_truncates():
    stm = InMemorySTM(window_size=3, max_tokens=10000)

    # Store 5 rounds (10 messages)
    for i in range(5):
        await stm.store("sess_1", "user", f"question {i}")
        await stm.store("sess_1", "assistant", f"answer {i}")

    history = await stm.recall("sess_1", "query", max_turns=3)
    # Should return at most 3 * 2 = 6 entries (last 3 rounds)
    assert len(history) == 6
    # Should be the most recent entries
    assert history[0]["content"] == "question 2"
    assert history[-1]["content"] == "answer 4"


@pytest.mark.asyncio
async def test_window_size_limits_storage():
    stm = InMemorySTM(window_size=2, max_tokens=10000)

    for i in range(5):
        await stm.store("sess_1", "user", f"msg {i}")

    # Internal store should be trimmed to window_size * 2 = 4
    assert len(stm._store["sess_1"]) == 4
    assert stm._store["sess_1"][0].content == "msg 1"


# ── Token Budget ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_token_budget_truncates():
    stm = InMemorySTM(window_size=100, max_tokens=20)

    # Each Chinese message ~20 tokens, budget is 20
    await stm.store("sess_1", "user", "这是一条消息")
    await stm.store("sess_1", "assistant", "这是回复消息")
    await stm.store("sess_1", "user", "第二轮对话")
    await stm.store("sess_1", "assistant", "第二轮回复")

    history = await stm.recall("sess_1", "query")
    # Should truncate due to token budget
    assert len(history) < 4


@pytest.mark.asyncio
async def test_large_token_budget_returns_all():
    stm = InMemorySTM(window_size=10, max_tokens=100000)

    await stm.store("sess_1", "user", "hello")
    await stm.store("sess_1", "assistant", "hi")

    history = await stm.recall("sess_1", "query")
    assert len(history) == 2


# ── Summary ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_summary_none_by_default():
    stm = InMemorySTM()
    assert await stm.get_summary("sess_1") is None


@pytest.mark.asyncio
async def test_set_and_get_summary():
    stm = InMemorySTM()
    await stm.set_summary("sess_1", "讨论了天气")
    assert await stm.get_summary("sess_1") == "讨论了天气"


@pytest.mark.asyncio
async def test_clear_removes_everything():
    stm = InMemorySTM()
    await stm.store("sess_1", "user", "hello")
    await stm.set_summary("sess_1", "summary")

    await stm.clear("sess_1")
    assert await stm.recall("sess_1", "query") == []
    assert await stm.get_summary("sess_1") is None


# ── Multiple Sessions ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sessions_isolated():
    stm = InMemorySTM()
    await stm.store("sess_1", "user", "hello from 1")
    await stm.store("sess_2", "user", "hello from 2")

    history1 = await stm.recall("sess_1", "q")
    history2 = await stm.recall("sess_2", "q")

    assert len(history1) == 1
    assert len(history2) == 1
    assert history1[0]["content"] == "hello from 1"
    assert history2[0]["content"] == "hello from 2"


# ── MemoryEntry Model ────────────────────────────────────────────

def test_memory_entry_defaults():
    entry = MemoryEntry(role="user", content="test")
    assert entry.role == "user"
    assert entry.content == "test"
    assert entry.token_count == 0
    assert entry.timestamp  # auto-generated
