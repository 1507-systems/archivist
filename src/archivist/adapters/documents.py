"""Local document source adapter.

Scans a local directory for files (PDF, TXT, MD, DOCX) and extracts text.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from archivist.adapters.base import SourceAdapter
from archivist.config import SourceConfig
from archivist.models import DocumentContent, DocumentMeta
from archivist.processors.extractors import get_extractor

logger = logging.getLogger(__name__)


class DocumentAdapter(SourceAdapter):
    """Adapter for local document collections."""

    def __init__(
        self,
        source_config: SourceConfig,
        corpus_slug: str,
        data_dir: Path,
    ) -> None:
        self._config = source_config
        self._corpus_slug = corpus_slug
        self._data_dir = data_dir
        self._media_dir = data_dir / corpus_slug / "media"
        self._transcripts_dir = data_dir / corpus_slug / "transcripts"

    def source_type(self) -> str:
        return "documents"

    def discover(self) -> list[DocumentMeta]:
        """Scan the configured directory for matching files."""
        source_path = self._get_source_path()
        if not source_path.exists():
            logger.warning("Document source path does not exist: %s", source_path)
            return []

        extensions = set(self._config.extensions)
        documents: list[DocumentMeta] = []

        if self._config.recursive:
            files = sorted(source_path.rglob("*"))
        else:
            files = sorted(source_path.iterdir())

        for file_path in files:
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in extensions:
                continue

            # Build a slug from relative path
            rel = file_path.relative_to(source_path)
            slug = str(rel).replace("/", "-").replace(" ", "-")
            # Remove extension from slug
            slug = slug.rsplit(".", 1)[0] if "." in slug else slug

            doc_id = f"{self._corpus_slug}:0:{slug}"
            documents.append(
                DocumentMeta(
                    id=doc_id,
                    title=file_path.stem,
                    url=None,
                    metadata={"file_path": str(file_path), "extension": file_path.suffix.lower()},
                )
            )

        logger.info("Discovered %d documents in %s", len(documents), source_path)
        return documents

    def fetch(self, document: DocumentMeta) -> DocumentContent:
        """Extract text from a local file."""
        file_path = Path(document.metadata.get("file_path", ""))
        if not file_path.exists():
            logger.warning("File not found: %s", file_path)
            return DocumentContent(meta=document, text="", content_type="document")

        extension = document.metadata.get("extension", file_path.suffix.lower())
        extractor = get_extractor(extension)

        try:
            text = extractor.extract(file_path)
        except Exception as e:
            logger.error("Failed to extract text from %s: %s", file_path, e)
            return DocumentContent(meta=document, text="", content_type="document")

        # Archive original if configured
        if self._config.archive_media:
            self._archive_file(document, file_path)

        # Save extracted text
        if text:
            self._save_text(document, text)

        return DocumentContent(
            meta=document,
            text=text,
            content_type="document",
            raw_path=file_path,
        )

    def _get_source_path(self) -> Path:
        """Resolve the source directory path."""
        if not self._config.path:
            msg = "Document source requires a 'path' field"
            raise ValueError(msg)
        return Path(self._config.path).expanduser()

    def _archive_file(self, document: DocumentMeta, source_path: Path) -> None:
        """Copy the original file to media directory."""
        self._media_dir.mkdir(parents=True, exist_ok=True)
        slug = document.id.split(":")[-1]
        dest = self._media_dir / f"{slug}{source_path.suffix}"
        if not dest.exists():
            shutil.copy2(source_path, dest)
            logger.debug("Archived %s → %s", source_path, dest)

    def _save_text(self, document: DocumentMeta, text: str) -> None:
        """Save extracted text to transcripts directory."""
        self._transcripts_dir.mkdir(parents=True, exist_ok=True)
        slug = document.id.split(":")[-1]
        path = self._transcripts_dir / f"{slug}.txt"
        path.write_text(text, encoding="utf-8")
