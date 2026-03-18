"""Tests for the podcast source adapter."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from archivist.adapters.podcast import PodcastAdapter
from archivist.config import SourceConfig


@pytest.fixture
def podcast_config() -> SourceConfig:
    return SourceConfig(
        type="podcast",
        url="https://example.com/feed.xml",
        transcript_mode="fetch",
        transcript_url_pattern="https://example.com/transcripts/ep-{episode}.txt",
        archive_media=False,
        request_delay=0.0,  # No delay in tests
    )


@pytest.fixture
def adapter(podcast_config: SourceConfig, tmp_data_dir: Path) -> PodcastAdapter:
    return PodcastAdapter(
        source_config=podcast_config,
        corpus_slug="test-podcast",
        data_dir=tmp_data_dir,
    )


class TestPodcastAdapterDiscover:
    """Tests for episode discovery from RSS feeds."""

    def test_discover_from_feed(self, adapter: PodcastAdapter, fixtures_dir: Path) -> None:
        feed_xml = (fixtures_dir / "sample_feed.xml").read_text()
        # Parse BEFORE patching — the mock replaces feedparser.parse globally
        import feedparser
        parsed = feedparser.parse(feed_xml)

        with patch("archivist.adapters.podcast.feedparser.parse") as mock_parse:
            mock_parse.return_value = parsed
            documents = adapter.discover()

        assert len(documents) == 3
        # Episodes should have episode numbers in metadata
        ep_nums = [d.metadata.get("episode_number") for d in documents]
        assert 3 in ep_nums
        assert 2 in ep_nums
        assert 1 in ep_nums

    def test_discover_extracts_audio_urls(
        self, adapter: PodcastAdapter, fixtures_dir: Path,
    ) -> None:
        feed_xml = (fixtures_dir / "sample_feed.xml").read_text()
        import feedparser
        parsed = feedparser.parse(feed_xml)

        with patch("archivist.adapters.podcast.feedparser.parse") as mock_parse:
            mock_parse.return_value = parsed
            documents = adapter.discover()

        audio_urls = [d.metadata.get("audio_url") for d in documents]
        assert "https://example.com/audio/ep3.mp3" in audio_urls

    def test_discover_with_max_episodes(
        self, podcast_config: SourceConfig, tmp_data_dir: Path, fixtures_dir: Path
    ) -> None:
        podcast_config.max_episodes = 2
        adapter = PodcastAdapter(
            source_config=podcast_config,
            corpus_slug="test",
            data_dir=tmp_data_dir,
        )
        feed_xml = (fixtures_dir / "sample_feed.xml").read_text()
        import feedparser
        parsed = feedparser.parse(feed_xml)

        with patch("archivist.adapters.podcast.feedparser.parse") as mock_parse:
            mock_parse.return_value = parsed
            documents = adapter.discover()

        assert len(documents) == 2


class TestPodcastAdapterFetch:
    """Tests for episode transcript fetching."""

    def test_fetch_transcript_via_pattern(self, adapter: PodcastAdapter) -> None:
        from archivist.models import DocumentMeta

        doc = DocumentMeta(
            id="test-podcast:0:ep0042",
            title="Episode 42",
            url="https://example.com/ep42",
            metadata={"episode_number": 42},
        )

        mock_response = MagicMock()
        mock_response.text = "This is the transcript for episode 42."
        mock_response.status_code = 200

        with patch("archivist.adapters.podcast.create_client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client_fn.return_value = mock_client
            with patch("archivist.adapters.podcast.fetch_with_retry", return_value=mock_response):
                content = adapter.fetch(doc)

        assert content.text == "This is the transcript for episode 42."
        assert content.content_type == "transcript"

    def test_fetch_handles_404(self, adapter: PodcastAdapter) -> None:
        from archivist.models import DocumentMeta

        doc = DocumentMeta(
            id="test-podcast:0:ep9999",
            title="Episode 9999",
            metadata={"episode_number": 9999},
        )

        with patch("archivist.adapters.podcast.create_client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client_fn.return_value = mock_client
            with patch("archivist.adapters.podcast.fetch_with_retry", return_value=None):
                content = adapter.fetch(doc)

        assert content.text == ""


class TestEpisodeNumberExtraction:
    """Tests for episode number parsing from feed entries."""

    def test_from_itunes_tag(self, adapter: PodcastAdapter) -> None:
        entry = {"itunes_episode": "42", "title": "Some Title"}
        assert adapter._extract_episode_number(entry) == 42

    def test_from_title_hash(self, adapter: PodcastAdapter) -> None:
        entry = {"title": "My Podcast #123 - Topic"}
        assert adapter._extract_episode_number(entry) == 123

    def test_from_title_episode_word(self, adapter: PodcastAdapter) -> None:
        entry = {"title": "Episode 55: The Big One"}
        assert adapter._extract_episode_number(entry) == 55

    def test_no_episode_number(self, adapter: PodcastAdapter) -> None:
        entry = {"title": "Just a title"}
        assert adapter._extract_episode_number(entry) is None


class TestSlugGeneration:
    """Tests for slug generation from feed entries."""

    def test_slug_from_episode_number(self, adapter: PodcastAdapter) -> None:
        entry = {"itunes_episode": "42", "title": "Episode 42"}
        slug = adapter._make_slug(entry, 0)
        assert slug == "ep0042"

    def test_slug_from_title(self, adapter: PodcastAdapter) -> None:
        entry = {"title": "My Great Episode!"}
        slug = adapter._make_slug(entry, 0)
        assert "my-great-episode" in slug

    def test_slug_truncation(self, adapter: PodcastAdapter) -> None:
        entry = {"title": "A" * 100}
        slug = adapter._make_slug(entry, 0)
        assert len(slug) <= 60
