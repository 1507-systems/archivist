"""Abstract interface for vector storage backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from archivist.models import Chunk, SearchResult


class VectorStore(ABC):
    """Abstract interface for vector storage backends."""

    @abstractmethod
    def upsert(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        """Insert or update chunks with their embeddings."""

    @abstractmethod
    def search(
        self,
        query_embedding: list[float],
        n_results: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Search for similar chunks."""

    @abstractmethod
    def delete_document(self, document_id: str) -> None:
        """Remove all chunks for a document."""

    @abstractmethod
    def get_indexed_document_ids(self) -> set[str]:
        """Return IDs of all indexed documents (for incremental sync)."""

    @abstractmethod
    def collection_stats(self) -> dict[str, Any]:
        """Return statistics about the collection."""

    @abstractmethod
    def get_all_chunks(self) -> list[dict[str, Any]]:
        """Return all chunks with metadata (for export)."""
