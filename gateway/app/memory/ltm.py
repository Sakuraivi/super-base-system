"""Long-Term Memory: vector-backed persistent memory with semantic search."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from .chunker import TextChunker
from .embedding import EmbeddingProtocol
from .stm import estimate_tokens

logger = logging.getLogger(__name__)


class MemoryRecord(BaseModel):
    """A single memory record stored in LTM."""
    memory_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    content: str
    embedding: list[float] = Field(default_factory=list)
    session_id: str = ""
    tenant_id: str = "default"
    memory_type: str = "conversation"   # conversation / knowledge / decision
    source: str = ""                     # user / assistant / system
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    chunk_index: int = 0
    token_count: int = 0


class SearchResult(BaseModel):
    """A search result from LTM."""
    content: str
    score: float
    memory_id: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class LTMProtocol(Protocol):
    """Long-Term Memory async interface."""

    async def store(self, content: str, metadata: dict[str, Any]) -> str: ...
    async def search(self, query: str, top_k: int = 5) -> list[dict]: ...
    async def delete(self, memory_id: str) -> None: ...
    async def clear_session(self, session_id: str) -> None: ...


class InMemoryLTM:
    """In-memory LTM for fallback/testing. Simple cosine similarity search."""

    def __init__(self, embedding_client: EmbeddingProtocol):
        self._embedding = embedding_client
        self._records: dict[str, MemoryRecord] = {}

    async def store(self, content: str, metadata: dict[str, Any]) -> str:
        """Store a memory with embedding."""
        chunker = TextChunker()
        chunks = chunker.chunk(content)

        first_id = ""
        for i, chunk in enumerate(chunks):
            vec = await self._embedding.embed(chunk)
            record = MemoryRecord(
                content=chunk,
                embedding=vec,
                session_id=metadata.get("session_id", ""),
                tenant_id=metadata.get("tenant_id", "default"),
                memory_type=metadata.get("memory_type", "conversation"),
                source=metadata.get("source", ""),
                chunk_index=i,
                token_count=estimate_tokens(chunk),
            )
            self._records[record.memory_id] = record
            if i == 0:
                first_id = record.memory_id

        return first_id

    async def search(self, query: str, top_k: int = 5, tenant_id: str = "default") -> list[dict]:
        """Search by cosine similarity, filtered by tenant_id."""
        if not self._records:
            return []

        query_vec = await self._embedding.embed(query)
        scored = []

        for record in self._records.values():
            if record.tenant_id != tenant_id:
                continue
            if not record.embedding:
                continue
            score = self._cosine_similarity(query_vec, record.embedding)
            scored.append((score, record))

        scored.sort(key=lambda x: x[0], reverse=True)

        return [
            {
                "content": record.content,
                "score": score,
                "memory_id": record.memory_id,
                "metadata": {
                    "session_id": record.session_id,
                    "memory_type": record.memory_type,
                    "source": record.source,
                    "created_at": record.created_at,
                },
            }
            for score, record in scored[:top_k]
        ]

    async def delete(self, memory_id: str) -> None:
        self._records.pop(memory_id, None)

    async def clear_session(self, session_id: str) -> None:
        to_remove = [
            mid for mid, r in self._records.items()
            if r.session_id == session_id
        ]
        for mid in to_remove:
            del self._records[mid]

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)


class QdrantLTM:
    """LTM backed by Qdrant vector database.

    Requires: qdrant-client package and a running Qdrant instance.
    """

    COLLECTION = "long_term_memory"

    def __init__(
        self,
        embedding_client: EmbeddingProtocol,
        host: str = "localhost",
        port: int = 6333,
    ):
        self._embedding = embedding_client
        self._host = host
        self._port = port
        self._client = None
        self._chunker = TextChunker()

    async def _get_client(self):
        if self._client is None:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams

            self._client = QdrantClient(host=self._host, port=self._port)

            # Ensure collection exists
            collections = self._client.get_collections().collections
            exists = any(c.name == self.COLLECTION for c in collections)
            if not exists:
                self._client.create_collection(
                    collection_name=self.COLLECTION,
                    vectors_config=VectorParams(
                        size=self._embedding.dimension,
                        distance=Distance.COSINE,
                    ),
                )
                logger.info("[QdrantLTM] Created collection: %s", self.COLLECTION)

        return self._client

    async def store(self, content: str, metadata: dict[str, Any]) -> str:
        from qdrant_client.models import PointStruct

        client = await self._get_client()
        chunks = self._chunker.chunk(content)
        vectors = await self._embedding.embed_batch(chunks)

        points = []
        first_id = ""
        for i, (chunk, vec) in enumerate(zip(chunks, vectors)):
            point_id = uuid.uuid4().hex[:16]
            if i == 0:
                first_id = point_id

            points.append(PointStruct(
                id=point_id,
                vector=vec,
                payload={
                    "content": chunk,
                    "session_id": metadata.get("session_id", ""),
                    "tenant_id": metadata.get("tenant_id", "default"),
                    "memory_type": metadata.get("memory_type", "conversation"),
                    "source": metadata.get("source", ""),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "chunk_index": i,
                    "token_count": estimate_tokens(chunk),
                },
            ))

        if points:
            client.upsert(collection_name=self.COLLECTION, points=points)

        return first_id

    async def search(self, query: str, top_k: int = 5, tenant_id: str = "default") -> list[dict]:
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        client = await self._get_client()
        query_vec = await self._embedding.embed(query)

        results = client.search(
            collection_name=self.COLLECTION,
            query_vector=query_vec,
            limit=top_k,
            query_filter=Filter(
                must=[
                    FieldCondition(
                        key="tenant_id",
                        match=MatchValue(value=tenant_id),
                    )
                ]
            ),
        )

        return [
            {
                "content": hit.payload.get("content", ""),
                "score": hit.score,
                "memory_id": str(hit.id),
                "metadata": {
                    k: v for k, v in hit.payload.items()
                    if k != "content"
                },
            }
            for hit in results
        ]

    async def delete(self, memory_id: str) -> None:
        client = await self._get_client()
        client.delete(
            collection_name=self.COLLECTION,
            points_selector=[memory_id],
        )

    async def clear_session(self, session_id: str) -> None:
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        client = await self._get_client()
        client.delete(
            collection_name=self.COLLECTION,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="session_id",
                        match=MatchValue(value=session_id),
                    )
                ]
            ),
        )
