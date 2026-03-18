"""Tests for configuration loading and validation."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from archivist.config import (
    CorpusConfig,
    DefaultsConfig,
    GlobalConfig,
    SourceConfig,
    load_all_corpora,
    load_corpus_config,
    load_global_config,
    write_default_config,
)


class TestGlobalConfig:
    """Tests for global config loading."""

    def test_load_defaults_when_no_file(self, tmp_config_dir: Path) -> None:
        config = load_global_config(tmp_config_dir)
        assert config.defaults.chunk_size == 3200
        assert config.defaults.chunk_overlap == 400
        assert config.defaults.embedding_model == "all-mpnet-base-v2"
        assert config.defaults.vector_backend == "chromadb"

    def test_load_from_yaml(self, tmp_config_dir: Path) -> None:
        config_data = {
            "data_dir": "/tmp/test-data",
            "defaults": {
                "chunk_size": 1600,
                "chunk_overlap": 200,
                "embedding_model": "all-MiniLM-L6-v2",
            },
            "logging": {"level": "DEBUG"},
        }
        (tmp_config_dir / "config.yaml").write_text(yaml.dump(config_data))
        config = load_global_config(tmp_config_dir)
        assert config.data_dir == "/tmp/test-data"
        assert config.defaults.chunk_size == 1600
        assert config.logging.level == "DEBUG"

    def test_write_default_config(self, tmp_path: Path) -> None:
        config_dir = tmp_path / ".archivist"
        write_default_config(config_dir)
        assert (config_dir / "config.yaml").exists()
        assert (config_dir / "corpora").is_dir()
        assert (config_dir / "corpora" / "example.yaml.disabled").exists()


class TestCorpusConfig:
    """Tests for corpus config loading."""

    def test_load_corpus_from_yaml(self, fixtures_dir: Path) -> None:
        config = load_corpus_config(fixtures_dir / "sample_corpus.yaml")
        assert config.name == "Test Corpus"
        assert config.slug == "test-corpus"
        assert len(config.sources) == 1
        assert config.sources[0].type == "podcast"
        assert config.chunk_size == 1600

    def test_slug_derived_from_filename(self, tmp_config_dir: Path) -> None:
        corpus_data = {
            "name": "My Corpus",
            "sources": [{"type": "web", "url": "https://example.com"}],
        }
        path = tmp_config_dir / "corpora" / "my-corpus.yaml"
        path.write_text(yaml.dump(corpus_data))
        config = load_corpus_config(path)
        assert config.slug == "my-corpus"

    def test_effective_defaults(self) -> None:
        defaults = DefaultsConfig()
        corpus = CorpusConfig(
            name="Test",
            sources=[SourceConfig(type="web", url="https://example.com")],
            chunk_size=1000,
        )
        assert corpus.effective_chunk_size(defaults) == 1000
        assert corpus.effective_chunk_overlap(defaults) == 400  # Falls back to default
        assert corpus.effective_embedding_model(defaults) == "all-mpnet-base-v2"

    def test_load_all_corpora(self, tmp_config_dir: Path) -> None:
        corpora_dir = tmp_config_dir / "corpora"
        for name in ["alpha", "beta"]:
            data = {
                "name": name.title(),
                "sources": [{"type": "documents", "path": f"/tmp/{name}"}],
            }
            (corpora_dir / f"{name}.yaml").write_text(yaml.dump(data))

        corpora = load_all_corpora(tmp_config_dir)
        assert len(corpora) == 2
        assert "alpha" in corpora
        assert "beta" in corpora


class TestSourceConfig:
    """Tests for source config validation."""

    def test_valid_source_types(self) -> None:
        for source_type in ["podcast", "web", "documents"]:
            config = SourceConfig(type=source_type, url="https://example.com")
            assert config.type == source_type

    def test_invalid_source_type(self) -> None:
        with pytest.raises(ValueError, match="Source type must be one of"):
            SourceConfig(type="invalid", url="https://example.com")

    def test_podcast_source_defaults(self) -> None:
        config = SourceConfig(type="podcast", url="https://example.com/feed.xml")
        assert config.archive_media is False
        assert config.request_delay == 1.5

    def test_web_source_defaults(self) -> None:
        config = SourceConfig(type="web", url="https://example.com")
        assert config.crawl_depth == 2
        assert config.request_delay == 1.5

    def test_documents_source_defaults(self) -> None:
        config = SourceConfig(type="documents", path="/tmp/docs")
        assert config.recursive is True
        assert ".pdf" in config.extensions
