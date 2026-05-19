"""Memory factories: STM, LTM, and unified MemoryManager."""
from __future__ import annotations

import logging

from ..config import settings

logger = logging.getLogger(__name__)


def create_stm(window_size: int = 10, max_tokens: int = 2000):
    """Create STM instance (Redis if REDIS_URL is set, else in-memory)."""
    from .stm import InMemorySTM

    redis_url = settings.redis_url
    if redis_url and redis_url != "redis://localhost:6379/0":
        try:
            from .redis_stm import RedisSTM

            logger.info("[Factory] Using Redis STM: %s", redis_url)
            return RedisSTM(
                redis_url=redis_url,
                window_size=window_size,
                max_tokens=max_tokens,
            )
        except Exception as e:
            logger.warning("[Factory] Redis STM init failed (%s), falling back to in-memory", e)

    logger.warning(
        "[Factory] REDIS_URL not configured — using in-memory STM. "
        "Memory will be lost on restart. Set REDIS_URL for persistence."
    )
    return InMemorySTM(window_size=window_size, max_tokens=max_tokens)


def create_ltm():
    """Create LTM instance (Qdrant if available, else in-memory fallback)."""
    from .embedding import MockEmbeddingClient
    from .ltm import InMemoryLTM

    embedding = MockEmbeddingClient(dimension=settings.ltm_embedding_dimension)

    qdrant_host = settings.qdrant_host
    if qdrant_host and qdrant_host != "localhost":
        try:
            from .ltm import QdrantLTM

            logger.info("[Factory] Using Qdrant LTM: %s:%s", qdrant_host, settings.qdrant_port)
            return QdrantLTM(
                embedding_client=embedding,
                host=qdrant_host,
                port=settings.qdrant_port,
            )
        except Exception as e:
            logger.warning("[Factory] Qdrant LTM init failed (%s), falling back to in-memory", e)

    logger.warning(
        "[Factory] QDRANT_HOST not configured — using in-memory LTM. "
        "Long-term memories will be lost on restart. Set QDRANT_HOST for persistence."
    )
    return InMemoryLTM(embedding_client=embedding)


def create_memory_manager():
    """Create unified MemoryManager (STM + LTM)."""
    from .manager import MemoryManager

    stm = create_stm(
        window_size=settings.stm_window_size,
        max_tokens=settings.stm_max_tokens,
    )
    ltm = create_ltm()
    return MemoryManager(stm=stm, ltm=ltm)
