"""Text chunker for splitting content into overlapping segments."""
from __future__ import annotations


class TextChunker:
    """Split text into chunks with overlap, breaking at sentence boundaries.

    Args:
        chunk_size: Maximum characters per chunk.
        overlap: Number of characters to overlap between adjacent chunks.
    """

    def __init__(self, chunk_size: int = 512, overlap: int = 64):
        self._chunk_size = chunk_size
        self._overlap = overlap

    def chunk(self, text: str) -> list[str]:
        """Split text into overlapping chunks.

        Returns a single-element list if text fits in one chunk.
        Breaks at sentence boundaries (。.！!？?\n) when possible.
        """
        if not text or not text.strip():
            return []

        text = text.strip()
        if len(text) <= self._chunk_size:
            return [text]

        chunks = []
        start = 0

        while start < len(text):
            end = start + self._chunk_size

            if end >= len(text):
                # Last chunk
                chunks.append(text[start:])
                break

            # Try to break at a sentence boundary within the chunk
            boundary = self._find_boundary(text, start, end)
            if boundary > start:
                end = boundary

            chunks.append(text[start:end])
            # Next start = end - overlap
            start = max(end - self._overlap, start + 1)

        return chunks

    def _find_boundary(self, text: str, start: int, end: int) -> int:
        """Find the best sentence boundary within [start, end]."""
        # Search backwards from end for a sentence-ending punctuation
        search_zone = text[start:end]
        best = -1

        for delim in ("\n", "。", ".", "！", "!", "？", "?", "；", ";"):
            pos = search_zone.rfind(delim)
            if pos > best:
                best = pos

        if best > 0:
            # Include the delimiter in the current chunk
            return start + best + 1

        return end
