"""Tests for text extractors."""

from __future__ import annotations

from pathlib import Path

from archivist.processors.extractors import (
    HTMLToTextExtractor,
    MarkdownExtractor,
    PassthroughExtractor,
    get_extractor,
)


class TestHTMLToTextExtractor:
    """Tests for HTML text extraction."""

    def test_basic_extraction(self) -> None:
        html = "<html><body><p>Hello world</p></body></html>"
        extractor = HTMLToTextExtractor()
        text = extractor.extract(html)
        assert "Hello world" in text

    def test_strips_scripts_and_styles(self) -> None:
        html = """
        <html><body>
        <script>alert('bad');</script>
        <style>.foo { color: red; }</style>
        <p>Visible content</p>
        </body></html>
        """
        extractor = HTMLToTextExtractor()
        text = extractor.extract(html)
        assert "Visible content" in text
        assert "alert" not in text
        assert "color" not in text

    def test_strips_nav_elements(self) -> None:
        html = """
        <html><body>
        <nav><a href="/">Home</a></nav>
        <main><p>Main content</p></main>
        <footer><p>Footer</p></footer>
        </body></html>
        """
        extractor = HTMLToTextExtractor()
        text = extractor.extract(html)
        assert "Main content" in text
        assert "Home" not in text

    def test_from_file(self, fixtures_dir: Path) -> None:
        extractor = HTMLToTextExtractor()
        text = extractor.extract(fixtures_dir / "sample_page.html")
        assert "Welcome to the Test Page" in text
        assert "first paragraph" in text
        assert "console.log" not in text

    def test_collapses_blank_lines(self) -> None:
        html = "<p>One</p><p></p><p></p><p></p><p>Two</p>"
        extractor = HTMLToTextExtractor()
        text = extractor.extract(html)
        # Shouldn't have more than 2 consecutive newlines
        assert "\n\n\n" not in text


class TestMarkdownExtractor:
    """Tests for Markdown text extraction."""

    def test_strips_heading_markers(self) -> None:
        md = "# Heading 1\n## Heading 2\nPlain text"
        extractor = MarkdownExtractor()
        text = extractor.extract(md)
        assert "Heading 1" in text
        assert "#" not in text

    def test_converts_links(self) -> None:
        md = "Check out [this link](https://example.com) for details."
        extractor = MarkdownExtractor()
        text = extractor.extract(md)
        assert "this link" in text
        assert "https://example.com" not in text

    def test_strips_bold_italic(self) -> None:
        md = "This is **bold** and *italic* and ***both***."
        extractor = MarkdownExtractor()
        text = extractor.extract(md)
        assert "bold" in text
        assert "italic" in text
        assert "**" not in text
        assert "*" not in text.replace("both", "")  # Don't match the word

    def test_strips_code_fences(self) -> None:
        md = "Before\n```python\nprint('hello')\n```\nAfter"
        extractor = MarkdownExtractor()
        text = extractor.extract(md)
        assert "print('hello')" in text
        assert "```" not in text


class TestPassthroughExtractor:
    """Tests for passthrough text extraction."""

    def test_returns_text_unchanged(self) -> None:
        text = "Plain text content\nWith newlines"
        extractor = PassthroughExtractor()
        assert extractor.extract(text) == text

    def test_strips_whitespace(self) -> None:
        text = "  content  "
        extractor = PassthroughExtractor()
        assert extractor.extract(text) == "content"

    def test_handles_bytes(self) -> None:
        extractor = PassthroughExtractor()
        assert extractor.extract(b"bytes content") == "bytes content"


class TestGetExtractor:
    """Tests for extractor registry."""

    def test_html_extensions(self) -> None:
        assert isinstance(get_extractor(".html"), HTMLToTextExtractor)
        assert isinstance(get_extractor(".htm"), HTMLToTextExtractor)

    def test_markdown_extension(self) -> None:
        assert isinstance(get_extractor(".md"), MarkdownExtractor)

    def test_text_extension(self) -> None:
        assert isinstance(get_extractor(".txt"), PassthroughExtractor)

    def test_unknown_extension_returns_passthrough(self) -> None:
        assert isinstance(get_extractor(".xyz"), PassthroughExtractor)
