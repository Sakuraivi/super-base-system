"""Tests for Long-Term Memory: embedding, chunker, LTM, and MemoryManager."""
import pytest
import math
from app.memory.embedding import MockEmbeddingClient
from app.memory.chunker import TextChunker
from app.memory.ltm import InMemoryLTM, MemoryRecord
from app.memory.manager import MemoryManager
from app.memory.stm import InMemorySTM


# ── MockEmbeddingClient ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_embedding_deterministic():
    client = MockEmbeddingClient(dimension=64)
    v1 = await client.embed("hello world")
    v2 = await client.embed("hello world")
    assert v1 == v2


@pytest.mark.asyncio
async def test_embedding_different_texts():
    client = MockEmbeddingClient(dimension=64)
    v1 = await client.embed("hello")
    v2 = await client.embed("world")
    assert v1 != v2


@pytest.mark.asyncio
async def test_embedding_dimension():
    client = MockEmbeddingClient(dimension=128)
    vec = await client.embed("test")
    assert len(vec) == 128


@pytest.mark.asyncio
async def test_embedding_l2_normalized():
    client = MockEmbeddingClient(dimension=64)
    vec = await client.embed("normalize me")
    norm = math.sqrt(sum(x * x for x in vec))
    assert abs(norm - 1.0) < 1e-6


@pytest.mark.asyncio
async def test_embedding_batch():
    client = MockEmbeddingClient(dimension=32)
    texts = ["hello", "world", "test"]
    vectors = await client.embed_batch(texts)
    assert len(vectors) == 3
    assert len(vectors[0]) == 32
    # Each vector should match individual embed
    for text, vec in zip(texts, vectors):
        single = await client.embed(text)
        assert vec == single


# ── TextChunker ──────────────────────────────────────────────────

def test_chunker_short_text():
    chunker = TextChunker(chunk_size=100, overlap=10)
    chunks = chunker.chunk("short text")
    assert chunks == ["short text"]


def test_chunker_empty_text():
    chunker = TextChunker()
    assert chunker.chunk("") == []
    assert chunker.chunk("  ") == []


def test_chunker_long_text():
    chunker = TextChunker(chunk_size=50, overlap=10)
    text = "A" * 120
    chunks = chunker.chunk(text)
    assert len(chunks) > 1
    # All content should be covered
    reconstructed = chunks[0]
    for c in chunks[1:]:
        reconstructed += c[10:]  # overlap is 10
    assert len(reconstructed) >= 120


def test_chunker_sentence_boundary():
    chunker = TextChunker(chunk_size=20, overlap=5)
    text = "这是第一句话。这是第二句话。这是第三句话。"
    chunks = chunker.chunk(text)
    # Should break at sentence boundaries
    assert len(chunks) >= 2


def test_chunker_preserves_content():
    chunker = TextChunker(chunk_size=30, overlap=5)
    text = "Hello world. This is a test. Another sentence here."
    chunks = chunker.chunk(text)
    # All chunks should be substrings of original
    for chunk in chunks:
        assert chunk in text


# ── InMemoryLTM ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ltm_store_and_search():
    embedding = MockEmbeddingClient(dimension=64)
    ltm = InMemoryLTM(embedding_client=embedding)

    await ltm.store("Python is a programming language", {"session_id": "s1"})
    await ltm.store("The weather is sunny today", {"session_id": "s1"})

    results = await ltm.search("programming language", top_k=2)
    assert len(results) == 2
    # Mock embeddings are random, so scores may be negative — just verify structure
    assert "content" in results[0]
    assert "score" in results[0]
    assert "metadata" in results[0]


@pytest.mark.asyncio
async def test_ltm_search_returns_metadata():
    embedding = MockEmbeddingClient(dimension=64)
    ltm = InMemoryLTM(embedding_client=embedding)

    await ltm.store("important knowledge", {
        "session_id": "s1",
        "memory_type": "knowledge",
        "source": "user",
    })

    results = await ltm.search("knowledge", top_k=1)
    assert len(results) == 1
    assert results[0]["metadata"]["memory_type"] == "knowledge"
    assert results[0]["metadata"]["session_id"] == "s1"


@pytest.mark.asyncio
async def test_ltm_delete():
    embedding = MockEmbeddingClient(dimension=64)
    ltm = InMemoryLTM(embedding_client=embedding)

    memory_id = await ltm.store("to be deleted", {"session_id": "s1"})
    assert len(ltm._records) == 1

    await ltm.delete(memory_id)
    assert len(ltm._records) == 0


@pytest.mark.asyncio
async def test_ltm_clear_session():
    embedding = MockEmbeddingClient(dimension=64)
    ltm = InMemoryLTM(embedding_client=embedding)

    await ltm.store("session 1 memory", {"session_id": "s1"})
    await ltm.store("session 2 memory", {"session_id": "s2"})

    await ltm.clear_session("s1")
    assert len(ltm._records) == 1
    remaining = list(ltm._records.values())[0]
    assert remaining.session_id == "s2"


@pytest.mark.asyncio
async def test_ltm_search_empty():
    embedding = MockEmbeddingClient(dimension=64)
    ltm = InMemoryLTM(embedding_client=embedding)

    results = await ltm.search("anything", top_k=5)
    assert results == []


@pytest.mark.asyncio
async def test_ltm_cosine_similarity():
    embedding = MockEmbeddingClient(dimension=64)
    ltm = InMemoryLTM(embedding_client=embedding)

    # Same text should have similarity ~1.0
    vec = await embedding.embed("test")
    score = ltm._cosine_similarity(vec, vec)
    assert abs(score - 1.0) < 1e-6


# ── MemoryManager ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_manager_recall_returns_both():
    stm = InMemorySTM(window_size=10, max_tokens=2000)
    embedding = MockEmbeddingClient(dimension=64)
    ltm = InMemoryLTM(embedding_client=embedding)
    manager = MemoryManager(stm=stm, ltm=ltm)

    # Store in STM
    await stm.store("s1", "user", "hello")
    await stm.store("s1", "assistant", "hi")

    # Store in LTM
    await ltm.store("Python is great", {"session_id": "s1"})

    result = await manager.recall("s1", "Python programming")

    assert "conversation_history" in result
    assert "retrieved_memories" in result
    assert len(result["conversation_history"]) == 2
    assert len(result["retrieved_memories"]) > 0


@pytest.mark.asyncio
async def test_manager_store_interaction_always_stm():
    stm = InMemorySTM(window_size=10, max_tokens=2000)
    embedding = MockEmbeddingClient(dimension=64)
    ltm = InMemoryLTM(embedding_client=embedding)
    manager = MemoryManager(stm=stm, ltm=ltm)

    # Short messages: should go to STM only
    await manager.store_interaction("s1", "hi", "hello")

    history = await stm.recall("s1", "q")
    assert len(history) == 2
    # LTM should be empty (content too short)
    results = await ltm.search("hi", top_k=5)
    assert len(results) == 0


@pytest.mark.asyncio
async def test_manager_store_interaction_long_to_ltm():
    stm = InMemorySTM(window_size=10, max_tokens=2000)
    embedding = MockEmbeddingClient(dimension=64)
    ltm = InMemoryLTM(embedding_client=embedding)
    manager = MemoryManager(stm=stm, ltm=ltm)

    # Long messages: should go to both STM and LTM
    long_msg = "A" * 250  # > 200 chars threshold
    await manager.store_interaction("s1", long_msg, "short reply")

    history = await stm.recall("s1", "q")
    assert len(history) == 2

    results = await ltm.search(long_msg[:50], top_k=5)
    assert len(results) > 0


@pytest.mark.asyncio
async def test_manager_store_knowledge():
    stm = InMemorySTM()
    embedding = MockEmbeddingClient(dimension=64)
    ltm = InMemoryLTM(embedding_client=embedding)
    manager = MemoryManager(stm=stm, ltm=ltm)

    await manager.store_knowledge("s1", "Python is a programming language", source="user")

    results = await ltm.search("Python language", top_k=1)
    assert len(results) == 1
    assert results[0]["metadata"]["memory_type"] == "knowledge"
