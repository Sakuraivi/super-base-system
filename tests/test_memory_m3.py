"""Tests for M3: RAG enhancement, intent filtering, promotion, and session summary."""
import pytest
from app.memory.rag import Reranker, IntentFilter, deduplicate_results
from app.memory.manager import MemoryManager
from app.memory.stm import InMemorySTM
from app.memory.ltm import InMemoryLTM
from app.memory.embedding import MockEmbeddingClient


# ── Reranker ─────────────────────────────────────────────────────

def test_reranker_keyword_overlap():
    r = Reranker(alpha=0.5)
    results = [
        {"content": "Python is a programming language", "score": 0.8},
        {"content": "The weather is nice today", "score": 0.9},
    ]
    reranked = r.rerank("Python programming", results, top_k=2)
    # Python result should rank higher due to keyword overlap
    assert "Python" in reranked[0]["content"]


def test_reranker_empty_results():
    r = Reranker()
    assert r.rerank("test", [], top_k=5) == []


def test_reranker_no_keywords():
    r = Reranker()
    results = [{"content": "a", "score": 0.9}, {"content": "b", "score": 0.5}]
    reranked = r.rerank("的", results, top_k=2)  # Stopword only
    assert len(reranked) == 2
    assert reranked[0]["score"] >= reranked[1]["score"]


def test_reranker_top_k_limit():
    r = Reranker()
    results = [{"content": f"item {i}", "score": 0.5} for i in range(20)]
    reranked = r.rerank("item test", results, top_k=5)
    assert len(reranked) == 5


def test_reranker_blended_score():
    r = Reranker(alpha=0.7)
    results = [{"content": "test content here", "score": 0.5}]
    reranked = r.rerank("test", results, top_k=1)
    assert reranked[0]["score"] != 0.5  # Should be blended
    assert "semantic_score" in reranked[0]
    assert "keyword_score" in reranked[0]


# ── IntentFilter ─────────────────────────────────────────────────

def test_intent_filter_boosts_relevant():
    f = IntentFilter()
    f.register_module_keywords("weather", {"天气", "weather", "温度", "temperature"})

    results = [
        {"content": "今天天气很好", "score": 0.6},
        {"content": "Python programming", "score": 0.8},
    ]
    filtered = f.filter_by_intent(results, "weather")
    # Weather result should be boosted above Python
    assert "天气" in filtered[0]["content"]


def test_intent_filter_no_registered_module():
    f = IntentFilter()
    results = [{"content": "test", "score": 0.5}]
    filtered = f.filter_by_intent(results, "unknown_module")
    assert filtered == results  # Unchanged


def test_intent_filter_none_module():
    f = IntentFilter()
    results = [{"content": "test", "score": 0.5}]
    filtered = f.filter_by_intent(results, None)
    assert filtered == results


# ── Deduplication ────────────────────────────────────────────────

def test_deduplicate_removes_similar():
    results = [
        {"content": "Hello world test", "score": 0.9},
        {"content": "Hello world test", "score": 0.8},
        {"content": "Something completely different", "score": 0.7},
    ]
    deduped = deduplicate_results(results, threshold=0.95)
    assert len(deduped) == 2


def test_deduplicate_keeps_different():
    results = [
        {"content": "Python programming", "score": 0.9},
        {"content": "Weather forecast", "score": 0.8},
    ]
    deduped = deduplicate_results(results)
    assert len(deduped) == 2


def test_deduplicate_empty():
    assert deduplicate_results([]) == []


def test_deduplicate_single():
    results = [{"content": "only one", "score": 0.5}]
    assert deduplicate_results(results) == results


# ── MemoryManager: Smart Promotion ───────────────────────────────

@pytest.mark.asyncio
async def test_promote_by_length():
    stm = InMemorySTM()
    ltm = InMemoryLTM(embedding_client=MockEmbeddingClient(dimension=32))
    mgr = MemoryManager(stm=stm, ltm=ltm)

    long_msg = "这是一段很长的内容" * 20  # > 100 chars
    await mgr.store_interaction("s1", long_msg, "回复")

    results = await ltm.search("很长的内容", top_k=5)
    assert len(results) > 0


@pytest.mark.asyncio
async def test_promote_by_keyword():
    stm = InMemorySTM()
    ltm = InMemoryLTM(embedding_client=MockEmbeddingClient(dimension=32))
    mgr = MemoryManager(stm=stm, ltm=ltm)

    await mgr.store_interaction("s1", "这是一个重要决策", "同意")

    results = await ltm.search("重要决策", top_k=5)
    assert len(results) > 0


@pytest.mark.asyncio
async def test_no_promote_short_content():
    stm = InMemorySTM()
    ltm = InMemoryLTM(embedding_client=MockEmbeddingClient(dimension=32))
    mgr = MemoryManager(stm=stm, ltm=ltm)

    await mgr.store_interaction("s1", "hi", "hello")

    # STM should have it
    history = await stm.recall("s1", "q")
    assert len(history) == 2

    # LTM should NOT have it (too short, no keywords)
    results = await ltm.search("hi", top_k=5)
    assert len(results) == 0


@pytest.mark.asyncio
async def test_promote_by_substantive_answer():
    stm = InMemorySTM()
    ltm = InMemoryLTM(embedding_client=MockEmbeddingClient(dimension=32))
    mgr = MemoryManager(stm=stm, ltm=ltm)

    long_answer = "这是一个详细的回答，" * 20  # > 150 chars
    await mgr.store_interaction("s1", "问题", long_answer)

    results = await ltm.search("详细回答", top_k=5)
    assert len(results) > 0


# ── Session Summary / Promotion ──────────────────────────────────

@pytest.mark.asyncio
async def test_promote_session():
    stm = InMemorySTM(window_size=50, max_tokens=10000)
    ltm = InMemoryLTM(embedding_client=MockEmbeddingClient(dimension=32))
    mgr = MemoryManager(stm=stm, ltm=ltm)

    # Build a session history
    await stm.store("s1", "user", "What is Python?")
    await stm.store("s1", "assistant", "Python is a programming language.")
    await stm.store("s1", "user", "Tell me more")
    await stm.store("s1", "assistant", "Python was created by Guido van Rossum.")

    memory_id = await mgr.promote_session("s1")
    assert memory_id is not None

    # Summary should be in LTM
    results = await ltm.search("Python programming", top_k=5)
    assert len(results) > 0

    # Summary should be in STM
    summary = await stm.get_summary("s1")
    assert summary is not None
    assert "Python" in summary


@pytest.mark.asyncio
async def test_promote_empty_session():
    stm = InMemorySTM()
    ltm = InMemoryLTM(embedding_client=MockEmbeddingClient(dimension=32))
    mgr = MemoryManager(stm=stm, ltm=ltm)

    result = await mgr.promote_session("empty_session")
    assert result is None


# ── Recall with Reranking ────────────────────────────────────────

@pytest.mark.asyncio
async def test_recall_includes_reranked_memories():
    stm = InMemorySTM()
    ltm = InMemoryLTM(embedding_client=MockEmbeddingClient(dimension=32))
    mgr = MemoryManager(stm=stm, ltm=ltm)

    await stm.store("s1", "user", "hello")
    await ltm.store("Python is great for programming", {"session_id": "s1"})

    result = await mgr.recall("s1", "Python programming")
    assert len(result["conversation_history"]) == 1
    assert len(result["retrieved_memories"]) >= 1
    assert "score" in result["retrieved_memories"][0]


@pytest.mark.asyncio
async def test_recall_with_intent_filtering():
    stm = InMemorySTM()
    ltm = InMemoryLTM(embedding_client=MockEmbeddingClient(dimension=32))
    mgr = MemoryManager(stm=stm, ltm=ltm)
    mgr.intent_filter.register_module_keywords("weather", {"天气", "weather"})

    await ltm.store("今天天气很好，适合出门", {"session_id": "s1"})
    await ltm.store("Python is a great language", {"session_id": "s1"})

    result = await mgr.recall("s1", "天气怎么样", intent_module_id="weather")
    # Weather memory should be boosted
    assert len(result["retrieved_memories"]) > 0
