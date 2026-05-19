"""Memory Manager: unified interface combining STM and LTM with RAG enhancement."""
from __future__ import annotations

import logging
from typing import Any

from .stm import STMProtocol
from .ltm import LTMProtocol
from .rag import Reranker, IntentFilter, deduplicate_results

logger = logging.getLogger(__name__)

# Promotion thresholds
_PROMOTE_MIN_LENGTH = 100          # Minimum content length for auto-promotion
_PROMOTE_KEYWORDS = {              # Keywords that indicate high-value content
    "重要", "记住", "关键", "决策", "结论", "注意", "注意",
    "important", "remember", "key", "decision", "conclusion", "note",
}


class MemoryManager:
    """Unified memory management with RAG enhancement.

    Features:
    - recall(): STM + LTM with reranking and deduplication
    - store_interaction(): Smart promotion (length + keyword heuristics)
    - store_knowledge(): Explicit knowledge storage
    - promote_session(): Promote session summary to LTM on session end
    - evict_expired(): Clean up stale LTM records
    """

    def __init__(self, stm: STMProtocol, ltm: LTMProtocol):
        self._stm = stm
        self._ltm = ltm
        self._reranker = Reranker(alpha=0.7)
        self._intent_filter = IntentFilter()

    async def recall(
        self,
        session_id: str,
        query: str,
        max_turns: int = 10,
        ltm_top_k: int = 5,
        intent_module_id: str | None = None,
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        """Recall with RAG enhancement: reranking + deduplication + intent filtering."""
        # Step 1: Retrieve from both sources
        history = await self._stm.recall(session_id, query, max_turns=max_turns)
        raw_memories = await self._ltm.search(query, top_k=ltm_top_k * 2, tenant_id=tenant_id)

        # Step 2: Deduplicate
        unique_memories = deduplicate_results(raw_memories)

        # Step 3: Rerank (semantic + keyword blended score)
        reranked = self._reranker.rerank(query, unique_memories, top_k=ltm_top_k)

        # Step 4: Intent-aware filtering (boost relevant memories)
        if intent_module_id:
            reranked = self._intent_filter.filter_by_intent(reranked, intent_module_id)

        return {
            "conversation_history": history,
            "retrieved_memories": [
                {
                    "content": m["content"],
                    "score": round(m.get("score", 0.0), 4),
                    "memory_type": m.get("metadata", {}).get("memory_type", ""),
                }
                for m in reranked
            ],
        }

    async def store_interaction(
        self,
        session_id: str,
        user_msg: str,
        assistant_msg: str,
        tenant_id: str = "default",
    ) -> None:
        """Store with smart promotion heuristics.

        Promotion criteria (any one triggers LTM storage):
        - Content length > threshold
        - Contains high-value keywords (重要, 决策, 记住, etc.)
        - Is a question-answer pair with substantive answer
        """
        # Always store to STM
        await self._stm.store(session_id, "user", user_msg)
        await self._stm.store(session_id, "assistant", assistant_msg)

        # Evaluate promotion
        should_promote = self._should_promote(user_msg, assistant_msg)

        if should_promote:
            content = f"User: {user_msg}\nAssistant: {assistant_msg}"
            try:
                await self._ltm.store(
                    content=content,
                    metadata={
                        "session_id": session_id,
                        "memory_type": "conversation",
                        "source": "interaction",
                        "tenant_id": tenant_id,
                    },
                )
                logger.debug("[MemoryManager] Promoted interaction to LTM (session=%s)", session_id)
            except Exception as e:
                logger.warning("[MemoryManager] LTM store failed: %s", e)

    async def store_knowledge(
        self,
        session_id: str,
        content: str,
        source: str = "system",
    ) -> str:
        """Explicitly store a knowledge memory to LTM."""
        return await self._ltm.store(
            content=content,
            metadata={
                "session_id": session_id,
                "memory_type": "knowledge",
                "source": source,
            },
        )

    async def promote_session(self, session_id: str) -> str | None:
        """Promote session: generate summary from STM and store in LTM.

        Call this when a session ends to capture important context.
        """
        history = await self._stm.recall(session_id, "", max_turns=50)
        if not history:
            return None

        # Build summary from recent conversation
        summary_parts = []
        for msg in history[-10:]:  # Last 10 messages
            role = msg.get("role", "unknown")
            content = msg.get("content", "")[:200]  # Truncate long messages
            summary_parts.append(f"[{role}] {content}")

        summary = "\n".join(summary_parts)

        # Store summary in LTM
        memory_id = await self._ltm.store(
            content=summary,
            metadata={
                "session_id": session_id,
                "memory_type": "session_summary",
                "source": "system",
            },
        )

        # Store summary in STM for quick access
        await self._stm.set_summary(session_id, summary)

        return memory_id

    @staticmethod
    def _should_promote(user_msg: str, assistant_msg: str) -> bool:
        """Evaluate whether an interaction should be promoted to LTM."""
        combined = user_msg + assistant_msg

        # Length check
        if len(combined) > _PROMOTE_MIN_LENGTH:
            return True

        # Keyword check
        combined_lower = combined.lower()
        for kw in _PROMOTE_KEYWORDS:
            if kw in combined_lower:
                return True

        # Substantive Q&A: if assistant response is detailed
        if len(assistant_msg) > 150:
            return True

        return False

    @property
    def stm(self) -> STMProtocol:
        return self._stm

    @property
    def ltm(self) -> LTMProtocol:
        return self._ltm

    @property
    def intent_filter(self) -> IntentFilter:
        return self._intent_filter
