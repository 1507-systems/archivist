"""Tests for the web scraping source adapter."""

from __future__ import annotations

import re

from archivist.adapters.web import WebAdapter
from archivist.config import SourceConfig


class TestURLFiltering:
    """Tests for URL include/exclude pattern matching."""

    def test_url_matches_include(self) -> None:
        from pathlib import Path

        config = SourceConfig(
            type="web",
            url="https://example.com",
            include_patterns=["/docs/"],
            request_delay=0.0,
        )
        adapter = WebAdapter(config, "test", Path("/tmp/test"))
        include_re = [re.compile(p) for p in config.include_patterns]
        exclude_re = [re.compile(p) for p in config.exclude_patterns]

        assert adapter._url_matches_filters(
            "https://example.com/docs/page", include_re, exclude_re,
        )
        assert not adapter._url_matches_filters(
            "https://example.com/blog/post", include_re, exclude_re,
        )

    def test_url_matches_exclude(self) -> None:
        from pathlib import Path

        config = SourceConfig(
            type="web",
            url="https://example.com",
            exclude_patterns=["/api/"],
            request_delay=0.0,
        )
        adapter = WebAdapter(config, "test", Path("/tmp/test"))
        include_re = [re.compile(p) for p in config.include_patterns]
        exclude_re = [re.compile(p) for p in config.exclude_patterns]

        assert not adapter._url_matches_filters(
            "https://example.com/api/v1", include_re, exclude_re,
        )
        assert adapter._url_matches_filters("https://example.com/page", include_re, exclude_re)


class TestURLNormalization:
    """Tests for URL normalization."""

    def test_strips_fragment(self) -> None:
        from pathlib import Path

        config = SourceConfig(type="web", url="https://example.com")
        adapter = WebAdapter(config, "test", Path("/tmp/test"))
        assert adapter._normalize_url("https://example.com/page#section") == "https://example.com/page"

    def test_strips_trailing_slash(self) -> None:
        from pathlib import Path

        config = SourceConfig(type="web", url="https://example.com")
        adapter = WebAdapter(config, "test", Path("/tmp/test"))
        assert adapter._normalize_url("https://example.com/page/") == "https://example.com/page"

    def test_root_path(self) -> None:
        from pathlib import Path

        config = SourceConfig(type="web", url="https://example.com")
        adapter = WebAdapter(config, "test", Path("/tmp/test"))
        assert adapter._normalize_url("https://example.com/") == "https://example.com/"


class TestURLToSlug:
    """Tests for URL-to-slug conversion."""

    def test_simple_path(self) -> None:
        from pathlib import Path

        config = SourceConfig(type="web", url="https://example.com")
        adapter = WebAdapter(config, "test", Path("/tmp/test"))
        slug = adapter._url_to_slug("https://example.com/docs/getting-started")
        assert slug == "docs-getting-started"

    def test_root_url(self) -> None:
        from pathlib import Path

        config = SourceConfig(type="web", url="https://example.com")
        adapter = WebAdapter(config, "test", Path("/tmp/test"))
        assert adapter._url_to_slug("https://example.com/") == "index"


class TestLinkExtraction:
    """Tests for HTML link extraction."""

    def test_extracts_same_domain_links(self) -> None:
        from pathlib import Path

        config = SourceConfig(type="web", url="https://example.com")
        adapter = WebAdapter(config, "test", Path("/tmp/test"))

        html = """
        <a href="/page1">Page 1</a>
        <a href="https://example.com/page2">Page 2</a>
        <a href="https://other.com/external">External</a>
        """
        links = adapter._extract_links(html, "https://example.com/")
        assert "https://example.com/page1" in links
        assert "https://example.com/page2" in links
        # External links should be excluded
        assert not any("other.com" in link for link in links)

    def test_extracts_title(self) -> None:
        from pathlib import Path

        config = SourceConfig(type="web", url="https://example.com")
        adapter = WebAdapter(config, "test", Path("/tmp/test"))

        html = "<html><head><title>My Page</title></head><body></body></html>"
        assert adapter._extract_title(html) == "My Page"
