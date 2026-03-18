"""Web scraping source adapter.

Crawls websites starting from a seed URL, follows links up to a configurable
depth, and extracts text from HTML pages.
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

from archivist.adapters.base import SourceAdapter
from archivist.config import SourceConfig
from archivist.models import DocumentContent, DocumentMeta
from archivist.processors.extractors import HTMLToTextExtractor
from archivist.utils.http import create_client, fetch_with_retry

logger = logging.getLogger(__name__)


class WebAdapter(SourceAdapter):
    """Adapter for web page scraping with configurable crawl depth."""

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
        self._extractor = HTMLToTextExtractor()

    def source_type(self) -> str:
        return "web"

    def discover(self) -> list[DocumentMeta]:
        """Crawl from seed URL and discover pages up to crawl_depth."""
        if not self._config.url:
            msg = "Web source requires a 'url' field"
            raise ValueError(msg)

        seed_url = self._config.url
        max_depth = self._config.crawl_depth

        # If a sitemap is provided, use it for discovery
        if self._config.sitemap_url:
            return self._discover_from_sitemap(self._config.sitemap_url)

        # BFS crawl
        visited: set[str] = set()
        documents: list[DocumentMeta] = []
        queue: list[tuple[str, int]] = [(seed_url, 0)]  # (url, depth)

        include_re = [re.compile(p) for p in self._config.include_patterns]
        exclude_re = [re.compile(p) for p in self._config.exclude_patterns]

        client = create_client()
        try:
            while queue:
                url, depth = queue.pop(0)
                normalized = self._normalize_url(url)

                if normalized in visited:
                    continue
                visited.add(normalized)

                if not self._url_matches_filters(url, include_re, exclude_re):
                    continue

                logger.debug("Crawling (depth %d): %s", depth, url)
                time.sleep(self._config.request_delay)

                try:
                    response = fetch_with_retry(client, url, max_retries=2)
                except Exception as e:
                    logger.warning("Failed to fetch %s: %s", url, e)
                    continue

                if response is None:
                    continue

                content_type = response.headers.get("content-type", "")
                if "text/html" not in content_type:
                    continue

                slug = self._url_to_slug(url)
                doc_id = f"{self._corpus_slug}:0:{slug}"
                documents.append(
                    DocumentMeta(
                        id=doc_id,
                        title=self._extract_title(response.text) or url,
                        url=url,
                    )
                )

                # Follow links if under max depth
                if depth < max_depth:
                    links = self._extract_links(response.text, url)
                    for link in links:
                        if self._normalize_url(link) not in visited:
                            queue.append((link, depth + 1))
        finally:
            client.close()

        logger.info("Discovered %d pages from %s", len(documents), seed_url)
        return documents

    def fetch(self, document: DocumentMeta) -> DocumentContent:
        """Fetch and extract text from a web page."""
        if not document.url:
            return DocumentContent(meta=document, text="", content_type="webpage")

        client = create_client()
        try:
            response = fetch_with_retry(
                client, document.url, delay=self._config.request_delay
            )
            if response is None:
                return DocumentContent(meta=document, text="", content_type="webpage")

            html = response.text
            text = self._extractor.extract(html)

            # Archive HTML if configured
            if self._config.archive_media:
                self._archive_html(document, html)

            # Save extracted text
            if text:
                self._save_text(document, text)

            return DocumentContent(
                meta=document,
                text=text,
                content_type="webpage",
            )
        finally:
            client.close()

    def _discover_from_sitemap(self, sitemap_url: str) -> list[DocumentMeta]:
        """Parse a sitemap XML for URL discovery."""
        import xml.etree.ElementTree as ET

        client = create_client()
        try:
            response = fetch_with_retry(client, sitemap_url)
            if response is None:
                logger.warning("Sitemap not found: %s", sitemap_url)
                return []

            root = ET.fromstring(response.text)
            # Handle namespace in sitemap XML
            ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

            documents: list[DocumentMeta] = []
            for url_elem in root.findall(".//sm:url/sm:loc", ns):
                if url_elem.text:
                    url = url_elem.text.strip()
                    slug = self._url_to_slug(url)
                    doc_id = f"{self._corpus_slug}:0:{slug}"
                    documents.append(
                        DocumentMeta(id=doc_id, title=url, url=url)
                    )

            # Also check for plain <url><loc> without namespace
            if not documents:
                for url_elem in root.findall(".//url/loc"):
                    if url_elem.text:
                        url = url_elem.text.strip()
                        slug = self._url_to_slug(url)
                        doc_id = f"{self._corpus_slug}:0:{slug}"
                        documents.append(
                            DocumentMeta(id=doc_id, title=url, url=url)
                        )

            return documents
        finally:
            client.close()

    def _extract_links(self, html: str, base_url: str) -> list[str]:
        """Extract all <a href> links from HTML, resolved to absolute URLs."""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        base_domain = urlparse(base_url).netloc
        links: list[str] = []

        for a in soup.find_all("a", href=True):
            href = a["href"]
            absolute = urljoin(base_url, href)
            parsed = urlparse(absolute)

            # Only follow links on the same domain
            if parsed.netloc == base_domain and parsed.scheme in ("http", "https"):
                # Strip fragment
                clean = parsed._replace(fragment="").geturl()
                links.append(clean)

        return links

    def _extract_title(self, html: str) -> str | None:
        """Extract <title> from HTML."""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        title_tag = soup.find("title")
        if title_tag and hasattr(title_tag, "string") and title_tag.string:
            return str(title_tag.string).strip()
        return None

    def _url_matches_filters(
        self,
        url: str,
        include: list[re.Pattern[str]],
        exclude: list[re.Pattern[str]],
    ) -> bool:
        """Check if URL passes include/exclude filters."""
        if exclude and any(p.search(url) for p in exclude):
            return False
        return not (include and not any(p.search(url) for p in include))

    def _normalize_url(self, url: str) -> str:
        """Normalize a URL for deduplication."""
        parsed = urlparse(url)
        # Remove fragment, trailing slash, lowercase
        path = parsed.path.rstrip("/") or "/"
        return f"{parsed.scheme}://{parsed.netloc}{path}"

    def _url_to_slug(self, url: str) -> str:
        """Convert a URL to a filesystem-safe slug."""
        parsed = urlparse(url)
        path = parsed.path.strip("/").replace("/", "-") or "index"
        slug = re.sub(r"[^\w-]", "", path)
        return slug[:80] or "page"

    def _archive_html(self, document: DocumentMeta, html: str) -> None:
        """Save raw HTML to media directory."""
        self._media_dir.mkdir(parents=True, exist_ok=True)
        slug = document.id.split(":")[-1]
        path = self._media_dir / f"{slug}.html"
        path.write_text(html, encoding="utf-8")

    def _save_text(self, document: DocumentMeta, text: str) -> None:
        """Save extracted text to transcripts directory."""
        self._transcripts_dir.mkdir(parents=True, exist_ok=True)
        slug = document.id.split(":")[-1]
        path = self._transcripts_dir / f"{slug}.txt"
        path.write_text(text, encoding="utf-8")
