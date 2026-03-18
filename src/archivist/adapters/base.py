"""Abstract base class for source adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod

from archivist.models import DocumentContent, DocumentMeta


class SourceAdapter(ABC):
    """Base class for all source adapters.

    Each adapter knows how to discover documents from a specific source type
    (podcast feed, website, local directory) and fetch their content as text.
    """

    @abstractmethod
    def discover(self) -> list[DocumentMeta]:
        """Discover available documents from the source.

        Returns metadata for all documents without downloading content.
        Used for incremental sync — compare against already-indexed documents.
        """

    @abstractmethod
    def fetch(self, document: DocumentMeta) -> DocumentContent:
        """Fetch the full content of a single document.

        Downloads, extracts, or transcribes as needed.
        Returns processed text ready for chunking.
        """

    @abstractmethod
    def source_type(self) -> str:
        """Return the source type identifier (e.g., 'podcast', 'web', 'documents')."""
