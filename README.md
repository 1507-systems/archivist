# Archivist

A self-hosted, open-source corpus-building tool that scrapes content sources, processes them into searchable text, generates embeddings, and exposes them via MCP server and REST API.

## Features

- **Source adapters**: Podcast RSS feeds, websites (with crawl depth), local document collections (PDF, TXT, MD, DOCX)
- **Processing pipeline**: Text extraction, configurable chunking with overlap, local embedding generation
- **Vector search**: ChromaDB-backed semantic search with cosine similarity
- **MCP server**: Expose corpora to Claude Code and Claude Desktop via Model Context Protocol
- **REST API**: Optional FastAPI server with bearer token auth
- **CLI-first**: All functionality accessible from the command line
- **Idempotent**: Every operation is safe to re-run — incremental sync by default
- **Docker support**: Docker Compose for containerized deployment

## Quick Start

### Install

```bash
pip install -e .
```

### Initialize

```bash
archivist init
```

This creates `~/.archivist/` with a default config and example corpus.

### Add a Corpus

```bash
archivist add my-podcast
```

Or manually create `~/.archivist/corpora/my-podcast.yaml`:

```yaml
name: My Podcast Archive
description: Full transcript archive of My Podcast

sources:
  - type: podcast
    url: https://example.com/feed.xml
    transcript_mode: whisper
    archive_media: false
```

### Sync

```bash
archivist sync my-podcast    # Sync one corpus
archivist sync               # Sync all corpora
```

### Search

```bash
archivist search "how does TLS work" --corpus my-podcast
```

### Serve (MCP)

```bash
archivist serve              # stdio (for Claude Code/Desktop)
archivist serve --transport sse --port 8091   # SSE (for remote access)
```

### REST API

```bash
archivist api --port 8090
```

## Configuration

### Global Config (`~/.archivist/config.yaml`)

```yaml
data_dir: ~/.archivist/data    # Where corpus data is stored

defaults:
  chunk_size: 3200             # ~800 tokens per chunk
  chunk_overlap: 400           # ~100 tokens overlap
  embedding_model: all-mpnet-base-v2
  vector_backend: chromadb

logging:
  level: INFO
```

### Source Types

**Podcast** — RSS feed with transcript fetching or Whisper transcription:

```yaml
sources:
  - type: podcast
    url: https://example.com/feed.xml
    transcript_mode: fetch     # fetch | whisper | none
    transcript_url_pattern: "https://example.com/transcripts/ep-{episode}.txt"
    archive_media: false
```

**Web** — Website crawling with configurable depth:

```yaml
sources:
  - type: web
    url: https://docs.example.com/
    crawl_depth: 2
    include_patterns: ["/docs/"]
    exclude_patterns: ["/api/"]
```

**Documents** — Local file collection:

```yaml
sources:
  - type: documents
    path: ~/Documents/papers
    extensions: [.pdf, .txt, .md]
    recursive: true
```

## Docker

```bash
docker compose up
```

Services:
- `archivist` — MCP server on port 8091
- `api` — REST API on port 8090

Mount your config directory and set `ARCHIVIST_API_TOKEN` for the API.

## CLI Reference

| Command | Description |
|---------|-------------|
| `archivist init` | Initialize config directory |
| `archivist add <name>` | Create corpus config interactively |
| `archivist sync [name]` | Sync one or all corpora |
| `archivist search "query"` | Semantic search across corpora |
| `archivist status` | Show all corpora and stats |
| `archivist serve` | Start MCP server |
| `archivist api` | Start REST API |
| `archivist export <corpus> <format>` | Export to JSON or CSV |

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Type checking
mypy src/

# Linting
ruff check src/ tests/
```

## Architecture

See [SPEC.md](SPEC.md) for the full specification.

```
Subject Area (corpus)
  └── Sources (one or many, any type)
       └── Documents (individual items)
            └── Chunks (embedded, searchable)
```

## License

MIT
