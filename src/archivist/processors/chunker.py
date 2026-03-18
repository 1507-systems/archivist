"""Text chunking with configurable size, overlap, and boundary detection."""

from __future__ import annotations

from typing import Any

from archivist.models import Chunk


def chunk_text(
    text: str,
    document_id: str,
    *,
    chunk_size: int = 3200,
    chunk_overlap: int = 400,
    metadata: dict[str, Any] | None = None,
) -> list[Chunk]:
    """Split text into overlapping chunks, preferring paragraph boundaries.

    Tries to break on paragraph boundaries (double newline) when possible.
    Falls back to breaking on single newlines, then on spaces, then on
    the exact chunk_size boundary.

    Args:
        text: The full text to chunk.
        document_id: Document ID to include in chunk IDs.
        chunk_size: Target characters per chunk (~800 tokens at 4 chars/token).
        chunk_overlap: Characters of overlap between adjacent chunks.
        metadata: Additional metadata to attach to each chunk.

    Returns:
        List of Chunk objects with sequential IDs.
    """
    if not text or not text.strip():
        return []

    text = text.strip()

    # If the text fits in one chunk, return it directly
    if len(text) <= chunk_size:
        return [
            Chunk(
                id=f"{document_id}:chunk0000",
                text=text,
                document_id=document_id,
                chunk_index=0,
                metadata=metadata or {},
            )
        ]

    chunks: list[Chunk] = []
    start = 0

    while start < len(text):
        # Determine end of this chunk
        end = min(start + chunk_size, len(text))

        # If we're not at the end of the text, try to find a good break point
        if end < len(text):
            end = _find_break_point(text, start, end)

        chunk_text_content = text[start:end].strip()
        if chunk_text_content:
            chunk_id = f"{document_id}:chunk{len(chunks):04d}"
            chunks.append(
                Chunk(
                    id=chunk_id,
                    text=chunk_text_content,
                    document_id=document_id,
                    chunk_index=len(chunks),
                    metadata=metadata or {},
                )
            )

        # Move start forward, accounting for overlap
        if end >= len(text):
            break
        start = end - chunk_overlap
        # Don't go backwards
        if start <= (end - chunk_size):
            start = end

    return chunks


def _find_break_point(text: str, start: int, end: int) -> int:
    """Find the best break point near `end`, searching backwards.

    Priority: paragraph boundary > single newline > space > exact boundary.
    Only searches within the last 20% of the chunk to avoid tiny chunks.
    """
    search_start = start + int((end - start) * 0.8)

    # Try paragraph boundary (double newline)
    pos = text.rfind("\n\n", search_start, end)
    if pos != -1:
        return pos + 2  # Include the newlines

    # Try single newline
    pos = text.rfind("\n", search_start, end)
    if pos != -1:
        return pos + 1

    # Try space
    pos = text.rfind(" ", search_start, end)
    if pos != -1:
        return pos + 1

    # No good break point found; break at exact boundary
    return end
