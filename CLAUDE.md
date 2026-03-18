# Archivist

A self-hosted corpus-building tool for semantic search and RAG.

## Status

**v0.1.0** — Core implementation complete. All source adapters, processing pipeline, vector store,
CLI, MCP server, and REST API are functional.

## Tech Stack

- Python 3.12, strict mypy, ruff linting
- Click (CLI), ChromaDB (vectors), sentence-transformers (embeddings)
- FastAPI (REST API), MCP Python SDK (MCP server)
- feedparser (RSS), httpx + BeautifulSoup (web), pymupdf (PDF)
- pytest for testing

## Development

```bash
# Setup
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Run tests
pytest

# Type checking
mypy src/

# Linting
ruff check src/ tests/
```

## Architecture

Config-driven corpus builder with pluggable source adapters:

```
~/.archivist/config.yaml          → Global settings
~/.archivist/corpora/<name>.yaml  → Per-corpus source definitions
```

Pipeline: discover → fetch → extract → chunk → embed → store → search

Source types: `podcast`, `web`, `documents`

## Conventions

- Conventional commits (feat:, fix:, chore:, etc.)
- Type hints everywhere, strict mypy
- Tests for all new functionality
- Keep modules focused — one purpose per file
- See SPEC.md for full specification
