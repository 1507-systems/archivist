"""Podcast/RSS source adapter.

Generalizes the SNaI download pipeline: parse RSS feed, discover episodes,
fetch transcripts (via URL pattern or Whisper), optionally archive audio.
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Any

import feedparser
import httpx

from archivist.adapters.base import SourceAdapter
from archivist.config import SourceConfig
from archivist.models import DocumentContent, DocumentMeta
from archivist.utils.http import create_client, fetch_with_retry

logger = logging.getLogger(__name__)


class PodcastAdapter(SourceAdapter):
    """Adapter for podcast RSS feeds."""

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
        return "podcast"

    def discover(self) -> list[DocumentMeta]:
        """Parse the RSS feed and return metadata for all episodes."""
        if not self._config.url:
            msg = "Podcast source requires a 'url' field"
            raise ValueError(msg)

        logger.info("Fetching RSS feed: %s", self._config.url)
        feed = feedparser.parse(self._config.url)

        if feed.bozo and not feed.entries:
            msg = f"Failed to parse RSS feed: {feed.bozo_exception}"
            raise ValueError(msg)

        documents: list[DocumentMeta] = []
        for i, entry in enumerate(feed.entries):
            # Try to extract episode number from title or itunes metadata
            episode_num = self._extract_episode_number(entry)
            doc_id = f"{self._corpus_slug}:0:{self._make_slug(entry, i)}"

            # Find audio enclosure URL
            audio_url = None
            for link in entry.get("links", []):
                if link.get("type", "").startswith("audio/"):
                    audio_url = link.get("href")
                    break
            if not audio_url:
                for enc in entry.get("enclosures", []):
                    if enc.get("type", "").startswith("audio/"):
                        audio_url = enc.get("href")
                        break

            metadata: dict[str, Any] = {
                "episode_number": episode_num,
                "audio_url": audio_url,
            }

            documents.append(
                DocumentMeta(
                    id=doc_id,
                    title=entry.get("title", f"Episode {i}"),
                    url=entry.get("link"),
                    published=self._parse_date(entry),
                    metadata=metadata,
                )
            )

        # Apply max_episodes limit
        if self._config.max_episodes:
            documents = documents[: self._config.max_episodes]

        logger.info("Discovered %d episodes from feed", len(documents))
        return documents

    def fetch(self, document: DocumentMeta) -> DocumentContent:
        """Fetch transcript for a single episode.

        Depending on transcript_mode:
        - fetch: Download transcript from URL pattern
        - whisper: Download audio and transcribe
        - none: Return empty text (metadata-only indexing)
        """
        mode = self._config.transcript_mode or "none"

        if mode == "fetch":
            text = self._fetch_transcript(document)
        elif mode == "whisper":
            text = self._whisper_transcribe(document)
        elif mode == "none":
            text = ""
        else:
            msg = f"Unknown transcript_mode: {mode}"
            raise ValueError(msg)

        # Archive audio if configured
        if self._config.archive_media:
            self._archive_audio(document)

        # Save transcript to disk for reference
        if text:
            self._save_transcript(document, text)

        return DocumentContent(
            meta=document,
            text=text,
            content_type="transcript",
        )

    def _fetch_transcript(self, document: DocumentMeta) -> str:
        """Download transcript from URL pattern."""
        pattern = self._config.transcript_url_pattern
        if not pattern:
            logger.warning("No transcript_url_pattern for fetch mode, skipping %s", document.id)
            return ""

        episode_num = document.metadata.get("episode_number")
        if episode_num is not None:
            url = pattern.format(episode=episode_num)
        else:
            logger.warning("No episode number for %s, cannot build transcript URL", document.id)
            return ""

        client = create_client()
        try:
            response = fetch_with_retry(
                client, url, delay=self._config.request_delay
            )
            if response is None:
                logger.warning("Transcript not found (404): %s", url)
                return ""
            return response.text
        except httpx.HTTPStatusError as e:
            logger.warning("Failed to fetch transcript %s: %s", url, e)
            return ""
        finally:
            client.close()

    def _whisper_transcribe(self, document: DocumentMeta) -> str:
        """Download audio and transcribe with Whisper."""
        audio_url = document.metadata.get("audio_url")
        if not audio_url:
            logger.warning("No audio URL for %s, cannot transcribe", document.id)
            return ""

        # Download audio
        audio_path = self._download_audio(document, audio_url)
        if not audio_path:
            return ""

        # Transcribe
        from archivist.processors.whisper import transcribe_audio
        return transcribe_audio(audio_path)

    def _download_audio(self, document: DocumentMeta, audio_url: str) -> Path | None:
        """Download audio file to media directory."""
        self._media_dir.mkdir(parents=True, exist_ok=True)
        slug = document.id.split(":")[-1]
        audio_path = self._media_dir / f"{slug}.mp3"

        if audio_path.exists():
            logger.debug("Audio already downloaded: %s", audio_path)
            return audio_path

        logger.info("Downloading audio: %s", audio_url)
        client = create_client()
        try:
            time.sleep(self._config.request_delay)
            with client.stream("GET", audio_url) as response:
                response.raise_for_status()
                with open(audio_path, "wb") as f:
                    for chunk in response.iter_bytes(chunk_size=262144):  # 256KB
                        f.write(chunk)
            logger.info("Downloaded audio: %s", audio_path.name)
            return audio_path
        except (httpx.HTTPError, OSError) as e:
            logger.error("Failed to download audio %s: %s", audio_url, e)
            return None
        finally:
            client.close()

    def _archive_audio(self, document: DocumentMeta) -> None:
        """Download and archive audio file (if not already downloaded)."""
        audio_url = document.metadata.get("audio_url")
        if audio_url:
            self._download_audio(document, audio_url)

    def _save_transcript(self, document: DocumentMeta, text: str) -> None:
        """Save transcript text to disk."""
        self._transcripts_dir.mkdir(parents=True, exist_ok=True)
        slug = document.id.split(":")[-1]
        path = self._transcripts_dir / f"{slug}.txt"
        path.write_text(text, encoding="utf-8")

    def _extract_episode_number(self, entry: Any) -> int | None:
        """Try to extract episode number from feed entry."""
        # Check itunes:episode tag
        ep = entry.get("itunes_episode")
        if ep:
            try:
                return int(ep)
            except (ValueError, TypeError):
                pass

        # Try to extract from title (e.g., "SN 571", "Episode 42", "#123")
        title = entry.get("title", "")
        patterns = [
            r"#(\d+)",
            r"[Ee]pisode\s+(\d+)",
            r"[Ee]p\.?\s*(\d+)",
            r"\b[A-Z]+\s+(\d+)\b",  # "SN 571" style
        ]
        for pattern in patterns:
            match = re.search(pattern, title)
            if match:
                return int(match.group(1))

        return None

    def _parse_date(self, entry: Any) -> None:
        """Parse published date from feed entry (returns None for now — feedparser provides
        time_struct which needs conversion, deferred to avoid complexity)."""
        return None

    def _make_slug(self, entry: Any, index: int) -> str:
        """Create a filesystem-safe slug from an entry."""
        episode_num = self._extract_episode_number(entry)
        if episode_num is not None:
            return f"ep{episode_num:04d}"

        # Fall back to index-based slug
        title = entry.get("title", f"entry-{index}")
        slug = re.sub(r"[^\w\s-]", "", title.lower())
        slug = re.sub(r"[\s_]+", "-", slug).strip("-")
        return slug[:60] or f"entry-{index}"
