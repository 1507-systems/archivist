"""Text extraction from various content types."""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from pathlib import Path

logger = logging.getLogger(__name__)


class TextExtractor(ABC):
    """Base class for text extractors."""

    @abstractmethod
    def extract(self, content: str | bytes | Path) -> str:
        """Extract plain text from the given content."""


class HTMLToTextExtractor(TextExtractor):
    """Extract readable text from HTML, stripping tags and boilerplate."""

    # Tags whose content should be completely removed
    SKIP_TAGS = {"script", "style", "nav", "header", "footer", "aside", "noscript"}
    # Tags that should insert a newline break
    BLOCK_TAGS = {"p", "div", "br", "h1", "h2", "h3", "h4", "h5", "h6",
                  "li", "tr", "blockquote", "pre", "section", "article"}

    def extract(self, content: str | bytes | Path) -> str:
        """Extract text from HTML string or file path."""
        if isinstance(content, Path):
            html = content.read_text(encoding="utf-8", errors="replace")
        elif isinstance(content, bytes):
            html = content.decode("utf-8", errors="replace")
        else:
            html = content

        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")

        # Remove script, style, nav, etc.
        for tag in soup.find_all(self.SKIP_TAGS):
            tag.decompose()

        text = soup.get_text(separator="\n", strip=True)
        # Collapse multiple blank lines into max two newlines
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


class PDFExtractor(TextExtractor):
    """Extract text from PDF files using pymupdf."""

    def extract(self, content: str | bytes | Path) -> str:
        """Extract text from a PDF file path."""
        import pymupdf

        if isinstance(content, (str, Path)):
            doc = pymupdf.open(str(content))  # type: ignore[no-untyped-call]
        elif isinstance(content, bytes):
            doc = pymupdf.open(stream=content, filetype="pdf")  # type: ignore[no-untyped-call]
        else:
            msg = f"PDFExtractor expects a file path or bytes, got {type(content)}"
            raise TypeError(msg)

        pages = []
        for page in doc:  # type: ignore[attr-defined]
            text = page.get_text()
            if text.strip():
                pages.append(text)
        doc.close()  # type: ignore[no-untyped-call]
        return "\n\n".join(pages)


class MarkdownExtractor(TextExtractor):
    """Extract text from Markdown by stripping formatting markers."""

    def extract(self, content: str | bytes | Path) -> str:
        """Extract text from Markdown content."""
        if isinstance(content, Path):
            text = content.read_text(encoding="utf-8", errors="replace")
        elif isinstance(content, bytes):
            text = content.decode("utf-8", errors="replace")
        else:
            text = content

        # Strip common markdown syntax but preserve readable structure
        # Remove image links ![alt](url) → alt
        text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)
        # Convert links [text](url) → text
        text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
        # Remove bold/italic markers
        text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)
        text = re.sub(r"_{1,3}([^_]+)_{1,3}", r"\1", text)
        # Remove heading markers
        text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
        # Remove horizontal rules
        text = re.sub(r"^[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)
        # Remove code fences (keep content)
        text = re.sub(r"```[^\n]*\n", "", text)
        text = re.sub(r"```", "", text)
        # Remove inline code backticks
        text = re.sub(r"`([^`]+)`", r"\1", text)
        return text.strip()


class PassthroughExtractor(TextExtractor):
    """Pass through plain text without modification."""

    def extract(self, content: str | bytes | Path) -> str:
        """Return text as-is."""
        if isinstance(content, Path):
            return content.read_text(encoding="utf-8", errors="replace").strip()
        if isinstance(content, bytes):
            return content.decode("utf-8", errors="replace").strip()
        return content.strip()


# Registry for file extension → extractor mapping
EXTRACTOR_REGISTRY: dict[str, type[TextExtractor]] = {
    ".html": HTMLToTextExtractor,
    ".htm": HTMLToTextExtractor,
    ".pdf": PDFExtractor,
    ".md": MarkdownExtractor,
    ".txt": PassthroughExtractor,
    ".text": PassthroughExtractor,
}


def get_extractor(extension: str) -> TextExtractor:
    """Return an extractor instance for the given file extension."""
    ext = extension.lower()
    if ext in EXTRACTOR_REGISTRY:
        return EXTRACTOR_REGISTRY[ext]()
    # Default to passthrough for unknown types
    logger.warning("No extractor for extension '%s', using passthrough", ext)
    return PassthroughExtractor()
