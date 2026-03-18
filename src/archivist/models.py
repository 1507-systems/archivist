"""Core data models for Archivist."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class DocumentMeta:
    """Lightweight metadata for a discovered document."""

    id: str
    title: str
    url: str | None = None
    published: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DocumentContent:
    """Full content of a fetched document."""

    meta: DocumentMeta
    text: str
    content_type: str  # transcript, webpage, document
    raw_path: Path | None = None


@dataclass
class Chunk:
    """An embedded, searchable fragment of a document."""

    id: str  # {document_id}:chunk{NNNN}
    text: str
    document_id: str
    chunk_index: int
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchResult:
    """A single search result from the vector store."""

    chunk_id: str
    document_id: str
    text: str
    similarity: float  # 0.0–1.0, higher = more relevant
    metadata: dict[str, Any] = field(default_factory=dict)
