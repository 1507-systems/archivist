"""Configuration loading and validation for Archivist."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator


# -- Directory resolution --

def get_config_dir() -> Path:
    """Return the config directory, respecting ARCHIVIST_CONFIG_DIR env var."""
    env = os.environ.get("ARCHIVIST_CONFIG_DIR")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".archivist"


def get_data_dir(config: GlobalConfig | None = None) -> Path:
    """Return the data directory from env var, config, or default."""
    env = os.environ.get("ARCHIVIST_DATA_DIR")
    if env:
        return Path(env).expanduser()
    if config and config.data_dir:
        return Path(config.data_dir).expanduser()
    return get_config_dir() / "data"


# -- Pydantic models for config validation --

class LoggingConfig(BaseModel):
    """Logging configuration."""

    level: str = "INFO"
    file: str | None = None


class DefaultsConfig(BaseModel):
    """Default settings for corpus processing."""

    chunk_size: int = 3200
    chunk_overlap: int = 400
    embedding_model: str = "all-mpnet-base-v2"
    vector_backend: str = "chromadb"


class GlobalConfig(BaseModel):
    """Top-level global configuration (~/.archivist/config.yaml)."""

    data_dir: str | None = None
    defaults: DefaultsConfig = Field(default_factory=DefaultsConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


class SourceConfig(BaseModel):
    """Configuration for a single source within a corpus."""

    type: str  # podcast, web, documents
    url: str | None = None
    path: str | None = None

    # Podcast-specific
    transcript_mode: str | None = None  # fetch, whisper, none
    transcript_url_pattern: str | None = None
    max_episodes: int | None = None

    # Web-specific
    crawl_depth: int = 2
    sitemap_url: str | None = None
    include_patterns: list[str] = Field(default_factory=list)
    exclude_patterns: list[str] = Field(default_factory=list)

    # Document-specific
    extensions: list[str] = Field(default_factory=lambda: [".pdf", ".txt", ".md", ".docx"])
    recursive: bool = True

    # Common
    archive_media: bool = False
    request_delay: float = 1.5

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        allowed = {"podcast", "web", "documents"}
        if v not in allowed:
            msg = f"Source type must be one of {allowed}, got '{v}'"
            raise ValueError(msg)
        return v


class CorpusConfig(BaseModel):
    """Configuration for a single corpus (~/.archivist/corpora/<name>.yaml)."""

    name: str
    description: str = ""
    slug: str | None = None  # Derived from filename if omitted
    sources: list[SourceConfig]

    # Per-corpus overrides
    chunk_size: int | None = None
    chunk_overlap: int | None = None
    embedding_model: str | None = None

    schedule: str | None = None  # Future: cron integration

    def effective_chunk_size(self, defaults: DefaultsConfig) -> int:
        """Return chunk_size with fallback to global default."""
        return self.chunk_size if self.chunk_size is not None else defaults.chunk_size

    def effective_chunk_overlap(self, defaults: DefaultsConfig) -> int:
        """Return chunk_overlap with fallback to global default."""
        return self.chunk_overlap if self.chunk_overlap is not None else defaults.chunk_overlap

    def effective_embedding_model(self, defaults: DefaultsConfig) -> str:
        """Return embedding_model with fallback to global default."""
        return self.embedding_model or defaults.embedding_model


# -- Loading functions --

def load_global_config(config_dir: Path | None = None) -> GlobalConfig:
    """Load the global config.yaml, returning defaults if file doesn't exist."""
    config_dir = config_dir or get_config_dir()
    config_path = config_dir / "config.yaml"
    if not config_path.exists():
        return GlobalConfig()
    with open(config_path) as f:
        raw = yaml.safe_load(f) or {}
    return GlobalConfig.model_validate(raw)


def load_corpus_config(path: Path) -> CorpusConfig:
    """Load a single corpus YAML file."""
    with open(path) as f:
        raw = yaml.safe_load(f) or {}
    corpus = CorpusConfig.model_validate(raw)
    # Derive slug from filename if not set
    if corpus.slug is None:
        corpus.slug = path.stem
    return corpus


def load_all_corpora(config_dir: Path | None = None) -> dict[str, CorpusConfig]:
    """Load all corpus configs from the corpora/ directory."""
    config_dir = config_dir or get_config_dir()
    corpora_dir = config_dir / "corpora"
    if not corpora_dir.exists():
        return {}
    corpora: dict[str, CorpusConfig] = {}
    for path in sorted(corpora_dir.glob("*.yaml")):
        corpus = load_corpus_config(path)
        slug = corpus.slug or path.stem
        corpora[slug] = corpus
    return corpora


def write_default_config(config_dir: Path) -> None:
    """Write a default config.yaml to the config directory."""
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "corpora").mkdir(exist_ok=True)

    config_path = config_dir / "config.yaml"
    if not config_path.exists():
        default: dict[str, Any] = {
            "data_dir": str(config_dir / "data"),
            "defaults": {
                "chunk_size": 3200,
                "chunk_overlap": 400,
                "embedding_model": "all-mpnet-base-v2",
                "vector_backend": "chromadb",
            },
            "logging": {
                "level": "INFO",
            },
        }
        with open(config_path, "w") as f:
            yaml.dump(default, f, default_flow_style=False, sort_keys=False)

    # Write example corpus config (commented out)
    example_path = config_dir / "corpora" / "example.yaml.disabled"
    if not example_path.exists():
        example = {
            "name": "Example Podcast Archive",
            "description": "An example corpus configuration",
            "sources": [
                {
                    "type": "podcast",
                    "url": "https://example.com/feed.xml",
                    "transcript_mode": "whisper",
                    "archive_media": False,
                },
            ],
        }
        with open(example_path, "w") as f:
            yaml.dump(example, f, default_flow_style=False, sort_keys=False)
