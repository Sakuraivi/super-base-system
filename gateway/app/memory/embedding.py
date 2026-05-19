"""Embedding client interface and implementations."""
from __future__ import annotations

import hashlib
import math
import random
from typing import Protocol, runtime_checkable


@runtime_checkable
class EmbeddingProtocol(Protocol):
    """Embedding client async interface."""

    @property
    def dimension(self) -> int: ...

    async def embed(self, text: str) -> list[float]: ...

    async def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


class MockEmbeddingClient:
    """Deterministic pseudo-embedding: hash → seed → random → L2 normalize.

    Same text always produces the same vector. Different texts produce
    different vectors. Vectors are L2-normalized to unit sphere for
    meaningful cosine similarity comparisons.

    Used for development/testing. Replace with RealEmbeddingClient for production.
    """

    def __init__(self, dimension: int = 384):
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed(self, text: str) -> list[float]:
        return self._generate(text)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self._generate(t) for t in texts]

    def _generate(self, text: str) -> list[float]:
        """Generate a deterministic L2-normalized vector from text."""
        seed = int(hashlib.sha256(text.encode("utf-8")).hexdigest(), 16) % (2**32)
        rng = random.Random(seed)
        vec = [rng.gauss(0, 1) for _ in range(self._dimension)]
        # L2 normalize
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0:
            vec = [x / norm for x in vec]
        return vec
