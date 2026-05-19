"""RAG enhancement: reranker and intent-aware filtering."""
from __future__ import annotations

import re
from typing import Any


class Reranker:
    """Rerank search results by combining semantic score with keyword overlap.

    Final score = alpha * semantic_score + (1 - alpha) * keyword_score
    where keyword_score = matched_keywords / total_keywords
    """

    def __init__(self, alpha: float = 0.7):
        self._alpha = alpha

    def rerank(
        self,
        query: str,
        results: list[dict[str, Any]],
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Rerank results by blended semantic + keyword score."""
        if not results:
            return []

        keywords = self._extract_keywords(query)
        if not keywords:
            # No keywords extracted, just sort by semantic score
            return sorted(results, key=lambda r: r.get("score", 0), reverse=True)[:top_k]

        reranked = []
        for result in results:
            semantic_score = result.get("score", 0.0)
            content = result.get("content", "")
            keyword_score = self._keyword_overlap(keywords, content)
            blended = self._alpha * semantic_score + (1 - self._alpha) * keyword_score

            reranked.append({
                **result,
                "score": blended,
                "semantic_score": semantic_score,
                "keyword_score": keyword_score,
            })

        reranked.sort(key=lambda r: r["score"], reverse=True)
        return reranked[:top_k]

    @staticmethod
    def _extract_keywords(text: str) -> set[str]:
        """Extract keywords from text. Removes stopwords and short words."""
        _stopwords = {
            "的", "了", "是", "在", "我", "有", "和", "就", "不", "人", "都",
            "一", "一个", "上", "也", "很", "到", "说", "要", "去", "你",
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "being", "have", "has", "had", "do", "does", "did", "will",
            "would", "could", "should", "may", "might", "can", "shall",
            "it", "its", "this", "that", "these", "those", "i", "he", "she",
            "we", "they", "you", "me", "him", "her", "us", "them", "my",
            "his", "her", "our", "their", "your", "and", "or", "but", "if",
            "then", "so", "for", "of", "to", "in", "on", "at", "by", "with",
            "from", "as", "into", "about", "how", "what", "when", "where",
            "who", "which", "why",
        }
        # Split on non-alphanumeric/non-CJK characters
        tokens = re.findall(r'[\w一-鿿]+', text.lower())
        return {t for t in tokens if len(t) > 1 and t not in _stopwords}

    @staticmethod
    def _keyword_overlap(keywords: set[str], content: str) -> float:
        """Calculate keyword overlap ratio."""
        if not keywords:
            return 0.0
        content_lower = content.lower()
        matched = sum(1 for kw in keywords if kw in content_lower)
        return matched / len(keywords)


class IntentFilter:
    """Filter LTM search results by relevance to detected intent/module."""

    def __init__(self):
        self._module_keywords: dict[str, set[str]] = {}

    def register_module_keywords(self, module_id: str, keywords: set[str]) -> None:
        """Register keywords associated with a module for intent filtering."""
        self._module_keywords[module_id] = keywords

    def filter_by_intent(
        self,
        results: list[dict[str, Any]],
        intent_module_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Filter results to prioritize intent-relevant memories.

        If intent_module_id has registered keywords, boost results containing
        those keywords. Non-relevant results are demoted but not removed.
        """
        if not intent_module_id or intent_module_id not in self._module_keywords:
            return results

        keywords = self._module_keywords[intent_module_id]
        if not keywords:
            return results

        boosted = []
        for result in results:
            content = result.get("content", "").lower()
            has_keyword = any(kw in content for kw in keywords)
            # Boost relevant results by multiplying score
            boost_factor = 1.5 if has_keyword else 0.8
            boosted.append({
                **result,
                "score": result.get("score", 0.0) * boost_factor,
                "intent_boosted": has_keyword,
            })

        boosted.sort(key=lambda r: r["score"], reverse=True)
        return boosted


def deduplicate_results(results: list[dict[str, Any]], threshold: float = 0.95) -> list[dict[str, Any]]:
    """Remove near-duplicate results based on content similarity.

    Simple approach: if two results have very similar content (>95% shared
    characters), keep the one with higher score.
    """
    if len(results) <= 1:
        return results

    unique = []
    seen_contents = []

    for result in results:
        content = result.get("content", "")
        is_dup = False
        for seen in seen_contents:
            if _content_similarity(content, seen) > threshold:
                is_dup = True
                break
        if not is_dup:
            unique.append(result)
            seen_contents.append(content)

    return unique


def _content_similarity(a: str, b: str) -> float:
    """Simple character-level Jaccard similarity."""
    if not a or not b:
        return 0.0
    set_a = set(a)
    set_b = set(b)
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0
