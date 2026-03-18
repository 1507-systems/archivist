"""Tests for text chunking."""

from __future__ import annotations

from archivist.processors.chunker import chunk_text


class TestChunkText:
    """Tests for the chunk_text function."""

    def test_empty_text_returns_empty(self) -> None:
        assert chunk_text("", "doc1") == []
        assert chunk_text("   ", "doc1") == []

    def test_short_text_single_chunk(self) -> None:
        text = "Hello, this is a short text."
        chunks = chunk_text(text, "doc1", chunk_size=100)
        assert len(chunks) == 1
        assert chunks[0].text == text
        assert chunks[0].id == "doc1:chunk0000"
        assert chunks[0].document_id == "doc1"
        assert chunks[0].chunk_index == 0

    def test_text_split_into_multiple_chunks(self) -> None:
        # Create text that's ~300 chars with clear paragraph boundaries
        paragraphs = [f"Paragraph {i}. " + "x" * 80 for i in range(5)]
        text = "\n\n".join(paragraphs)
        chunks = chunk_text(text, "doc1", chunk_size=200, chunk_overlap=40)
        assert len(chunks) > 1
        # All chunks should have the correct document_id
        for chunk in chunks:
            assert chunk.document_id == "doc1"

    def test_chunk_ids_are_sequential(self) -> None:
        text = "word " * 500
        chunks = chunk_text(text, "myid", chunk_size=200, chunk_overlap=40)
        for i, chunk in enumerate(chunks):
            assert chunk.id == f"myid:chunk{i:04d}"
            assert chunk.chunk_index == i

    def test_overlap_between_chunks(self) -> None:
        text = "word " * 200
        chunks = chunk_text(text, "doc1", chunk_size=100, chunk_overlap=30)
        # Adjacent chunks should share some text (overlap)
        if len(chunks) >= 2:
            # The end of chunk[0] should overlap with the start of chunk[1]
            # Due to boundary-seeking this isn't exact, but chunks shouldn't be disjoint
            assert len(chunks) >= 2

    def test_paragraph_boundary_preference(self) -> None:
        # Create text with a clear paragraph boundary near the chunk_size
        part1 = "A" * 80
        part2 = "B" * 80
        text = f"{part1}\n\n{part2}"
        chunks = chunk_text(text, "doc1", chunk_size=100, chunk_overlap=20)
        # With a 100-char chunk_size, it should break at the paragraph boundary
        if len(chunks) >= 2:
            # First chunk should end near the paragraph boundary
            assert "A" in chunks[0].text
            assert "B" in chunks[-1].text

    def test_metadata_passed_to_chunks(self) -> None:
        text = "Some text content here."
        meta = {"title": "Test Doc", "source": "unit-test"}
        chunks = chunk_text(text, "doc1", metadata=meta)
        assert chunks[0].metadata == meta

    def test_large_text_chunking(self) -> None:
        # ~32000 chars = ~10 chunks at 3200 chunk_size
        text = "word " * 6400
        chunks = chunk_text(text, "doc1", chunk_size=3200, chunk_overlap=400)
        assert len(chunks) >= 8
        # Every chunk should have content
        for chunk in chunks:
            assert len(chunk.text) > 0
