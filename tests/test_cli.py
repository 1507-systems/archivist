"""Tests for CLI commands."""

from __future__ import annotations

from pathlib import Path

import yaml
from click.testing import CliRunner

from archivist.cli import cli


class TestInitCommand:
    """Tests for the 'init' command."""

    def test_init_creates_config(self, tmp_path: Path) -> None:
        config_dir = tmp_path / ".archivist"
        runner = CliRunner()
        result = runner.invoke(cli, ["--config-dir", str(config_dir), "init"])
        assert result.exit_code == 0
        assert (config_dir / "config.yaml").exists()
        assert (config_dir / "corpora").is_dir()

    def test_init_idempotent(self, tmp_path: Path) -> None:
        config_dir = tmp_path / ".archivist"
        runner = CliRunner()
        # First init
        runner.invoke(cli, ["--config-dir", str(config_dir), "init"])
        # Second init should not fail
        result = runner.invoke(cli, ["--config-dir", str(config_dir), "init"])
        assert result.exit_code == 0
        assert "already exists" in result.output


class TestStatusCommand:
    """Tests for the 'status' command."""

    def test_status_no_corpora(self, tmp_path: Path) -> None:
        config_dir = tmp_path / ".archivist"
        config_dir.mkdir()
        (config_dir / "corpora").mkdir()
        (config_dir / "config.yaml").write_text(
            yaml.dump({"data_dir": str(tmp_path / "data")})
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["--config-dir", str(config_dir), "status"])
        assert result.exit_code == 0
        assert "No corpora configured" in result.output

    def test_status_with_corpus(self, tmp_path: Path) -> None:
        config_dir = tmp_path / ".archivist"
        config_dir.mkdir()
        corpora_dir = config_dir / "corpora"
        corpora_dir.mkdir()
        (config_dir / "config.yaml").write_text(
            yaml.dump({"data_dir": str(tmp_path / "data")})
        )
        (corpora_dir / "test.yaml").write_text(yaml.dump({
            "name": "Test Corpus",
            "sources": [{"type": "documents", "path": "/tmp/docs"}],
        }))

        runner = CliRunner()
        result = runner.invoke(cli, ["--config-dir", str(config_dir), "status"])
        assert result.exit_code == 0
        assert "Test Corpus" in result.output
