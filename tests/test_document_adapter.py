"""Tests for the local document source adapter."""

from __future__ import annotations

from pathlib import Path

import pytest

from archivist.adapters.documents import DocumentAdapter
from archivist.config import SourceConfig


@pytest.fixture
def doc_dir(tmp_path: Path) -> Path:
    """Create a temporary directory with test documents."""
    docs = tmp_path / "documents"
    docs.mkdir()
    (docs / "readme.txt").write_text("This is a plain text file.")
    (docs / "notes.md").write_text("# Notes\n\nSome markdown notes.")
    (docs / "image.png").write_bytes(b"\x89PNG")  # Not a text file
    subdir = docs / "subdir"
    subdir.mkdir()
    (subdir / "nested.txt").write_text("Nested document content.")
    return docs


@pytest.fixture
def adapter(doc_dir: Path, tmp_data_dir: Path) -> DocumentAdapter:
    config = SourceConfig(
        type="documents",
        path=str(doc_dir),
        extensions=[".txt", ".md"],
        recursive=True,
    )
    return DocumentAdapter(
        source_config=config,
        corpus_slug="test-docs",
        data_dir=tmp_data_dir,
    )


class TestDocumentAdapterDiscover:
    """Tests for document discovery."""

    def test_discovers_matching_files(self, adapter: DocumentAdapter) -> None:
        documents = adapter.discover()
        titles = [d.title for d in documents]
        assert "readme" in titles
        assert "notes" in titles

    def test_excludes_non_matching_extensions(self, adapter: DocumentAdapter) -> None:
        documents = adapter.discover()
        # .png should not be included
        extensions = [d.metadata.get("extension") for d in documents]
        assert ".png" not in extensions

    def test_discovers_nested_files(self, adapter: DocumentAdapter) -> None:
        documents = adapter.discover()
        titles = [d.title for d in documents]
        assert "nested" in titles

    def test_non_recursive(self, doc_dir: Path, tmp_data_dir: Path) -> None:
        config = SourceConfig(
            type="documents",
            path=str(doc_dir),
            extensions=[".txt", ".md"],
            recursive=False,
        )
        adapter = DocumentAdapter(
            source_config=config,
            corpus_slug="test",
            data_dir=tmp_data_dir,
        )
        documents = adapter.discover()
        titles = [d.title for d in documents]
        assert "nested" not in titles  # Subdirectory should be skipped

    def test_missing_directory(self, tmp_data_dir: Path) -> None:
        config = SourceConfig(
            type="documents",
            path="/nonexistent/path",
            extensions=[".txt"],
        )
        adapter = DocumentAdapter(
            source_config=config,
            corpus_slug="test",
            data_dir=tmp_data_dir,
        )
        documents = adapter.discover()
        assert documents == []


class TestDocumentAdapterFetch:
    """Tests for document text extraction."""

    def test_fetch_text_file(self, adapter: DocumentAdapter) -> None:
        documents = adapter.discover()
        txt_doc = next(d for d in documents if d.title == "readme")
        content = adapter.fetch(txt_doc)
        assert "plain text file" in content.text
        assert content.content_type == "document"

    def test_fetch_markdown_file(self, adapter: DocumentAdapter) -> None:
        documents = adapter.discover()
        md_doc = next(d for d in documents if d.title == "notes")
        content = adapter.fetch(md_doc)
        assert "markdown notes" in content.text

    def test_saves_transcript(self, adapter: DocumentAdapter, tmp_data_dir: Path) -> None:
        documents = adapter.discover()
        txt_doc = next(d for d in documents if d.title == "readme")
        adapter.fetch(txt_doc)
        # Check that transcript was saved
        transcript_dir = tmp_data_dir / "test-docs" / "transcripts"
        assert transcript_dir.exists()
        txt_files = list(transcript_dir.glob("*.txt"))
        assert len(txt_files) >= 1
