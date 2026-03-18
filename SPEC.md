# Archivist — Specification

> A self-hosted, open-source corpus-building tool that scrapes content sources, processes them into
> searchable text, generates embeddings, and exposes them via MCP server and REST API.

**Version**: 1.0
**Status**: Implementation
**License**: MIT

---

## 1. Overview

Archivist generalizes the pipeline pioneered in the SNaI podcast archive project — download source
content, process it into text, chunk it, embed it, and expose it for semantic search. It replaces
ad hoc scripts with a configurable, extensible framework that works for any content source.

### 1.1 Goals

- **Source-agnostic**: Podcast feeds, websites, local document collections — same pipeline.
- **Config-driven**: YAML manifests define corpora. No code changes for new sources.
- **Idempotent**: Every operation is safe to re-run. No orphaned partial state.
- **CLI-first**: All functionality accessible from the command line.
- **Extensible**: Pluggable source adapters, processors, and vector backends.
- **Self-hosted**: Runs on your hardware. No cloud dependencies required.

### 1.2 Non-Goals

- Real-time streaming ingestion
- Multi-user access control (single-operator tool)
- GUI / web dashboard (CLI + API only)
- Cloud-managed vector stores in v1.0 (pluggable interface allows future addition)

---

## 2. Core Concepts

### 2.1 Hierarchy

```
Subject Area (corpus)
  └── Sources (one or many, any type)
       └── Documents (individual items)
            └── Chunks (embedded, searchable)
```

| Concept        | Description                                                      | Example                           |
|--------------- |----------------------------------------------------------------- |---------------------------------- |
| Subject Area   | A named corpus — a logical collection of related content         | "Security Now Archive"            |
| Source         | A content origin within a corpus                                 | RSS feed, website, local folder   |
| Document       | A single item from a source                                      | Podcast episode, web page, PDF    |
| Chunk          | An embedded, searchable fragment of a document                   | ~800-token text segment           |

### 2.2 Identifiers

- **Corpus ID**: Kebab-case slug derived from corpus name (e.g., `snai`, `true-crime`)
- **Document ID**: `{corpus_id}:{source_index}:{document_slug}`
- **Chunk ID**: `{document_id}:chunk{NNNN}`

---

## 3. Directory Structure

Archivist separates syncable configuration from local-only data.

### 3.1 Config Directory

```
~/.archivist/                    # Syncable (iCloud, OneDrive, Dropbox, git)
├── config.yaml                  # Global settings
├── corpora/                     # One YAML per subject area
│   ├── snai.yaml
│   └── true-crime.yaml
└── schedules.yaml               # Cron/sync schedules (future)
```

### 3.2 Data Directory

```
/var/lib/archivist/              # Local data (configurable path, NOT synced)
├── snai/
│   ├── media/                   # Source files (audio, PDFs, HTML snapshots)
│   ├── transcripts/             # Processed text (transcriptions, extractions)
│   ├── chunks/                  # Chunked text (JSON, one file per document)
│   └── vectordb/                # ChromaDB collection
└── true-crime/
    └── ...
```

The data directory path is set in `config.yaml` and defaults to `~/.archivist/data/` for
single-machine setups.

---

## 4. Configuration

### 4.1 Global Config (`config.yaml`)

```yaml
# ~/.archivist/config.yaml
data_dir: /var/lib/archivist     # Where corpus data lives (default: ~/.archivist/data/)

defaults:
  chunk_size: 3200               # Characters per chunk (~800 tokens)
  chunk_overlap: 400             # Overlap between chunks (~100 tokens)
  embedding_model: all-mpnet-base-v2  # sentence-transformers model
  vector_backend: chromadb       # Default vector store

logging:
  level: INFO
  file: ~/.archivist/archivist.log
```

### 4.2 Corpus Config (`corpora/<name>.yaml`)

```yaml
# ~/.archivist/corpora/snai.yaml
name: Security Now Archive
description: Steve Gibson's Security Now podcast — full transcript archive
slug: snai                       # Optional; derived from filename if omitted

sources:
  - type: podcast
    url: https://feeds.twit.tv/sn.xml
    transcript_mode: fetch       # fetch | whisper | none
    transcript_url_pattern: "https://www.grc.com/sn/sn-{episode}.txt"
    archive_media: false

# Per-corpus overrides (optional)
chunk_size: 3200
chunk_overlap: 400
embedding_model: all-mpnet-base-v2

schedule: weekly                 # Future: cron integration
```

### 4.3 Source Types and Options

#### Podcast Source

```yaml
- type: podcast
  url: <RSS feed URL>
  transcript_mode: fetch | whisper | none
  transcript_url_pattern: <URL template with {episode}>  # Required if transcript_mode: fetch
  archive_media: true | false                             # Download and keep audio files
  max_episodes: null                                      # Limit episode count (null = all)
  request_delay: 1.5                                      # Seconds between HTTP requests
```

#### Web Source

```yaml
- type: web
  url: <starting URL>
  crawl_depth: 2                 # How many links deep to follow
  sitemap_url: null              # Optional sitemap for discovery
  include_patterns: []           # URL patterns to include (regex)
  exclude_patterns: []           # URL patterns to exclude (regex)
  archive_media: false
  request_delay: 1.0
```

#### Document Source

```yaml
- type: documents
  path: /path/to/documents       # Local directory
  extensions:                     # File types to process
    - .pdf
    - .txt
    - .md
    - .docx
  recursive: true                 # Traverse subdirectories
  archive_media: false            # Copy originals to data dir
```

---

## 5. Source Adapters

### 5.1 Interface

All source adapters implement a common interface:

```python
class SourceAdapter(ABC):
    """Base class for all source adapters."""

    @abstractmethod
    def discover(self) -> list[DocumentMeta]:
        """Discover available documents from the source.

        Returns metadata for all documents without downloading content.
        Used for incremental sync — compare against already-indexed documents.
        """

    @abstractmethod
    def fetch(self, document: DocumentMeta) -> DocumentContent:
        """Fetch the full content of a single document.

        Downloads, extracts, or transcribes as needed.
        Returns processed text ready for chunking.
        """

    @abstractmethod
    def source_type(self) -> str:
        """Return the source type identifier (e.g., 'podcast', 'web', 'documents')."""
```

### 5.2 Data Models

```python
@dataclass
class DocumentMeta:
    """Lightweight metadata for a discovered document."""
    id: str                      # Unique within the source
    title: str
    url: str | None              # Source URL (None for local files)
    published: datetime | None
    metadata: dict[str, Any]     # Source-specific metadata (episode number, etc.)

@dataclass
class DocumentContent:
    """Full content of a fetched document."""
    meta: DocumentMeta
    text: str                    # Extracted/transcribed text
    content_type: str            # transcript, webpage, document
    raw_path: Path | None        # Path to archived source file (if archive_media=True)
```

### 5.3 Adapter: Podcast

- Parses RSS feed (xml.etree.ElementTree or feedparser)
- Discovers episodes from feed entries
- Fetches transcripts via `transcript_url_pattern` (mode: fetch) or Whisper (mode: whisper)
- Optionally downloads audio to `media/` directory
- Polite crawling: configurable delay between requests
- End-of-archive detection: stops after 3 consecutive 404s (for pattern-based fetching)

### 5.4 Adapter: Web

- Starts from seed URL, follows links up to `crawl_depth`
- Respects `include_patterns` / `exclude_patterns` for URL filtering
- HTML-to-text via BeautifulSoup (strips nav, scripts, styles)
- Optional sitemap parsing for discovery
- Tier 1: httpx for static pages
- Tier 2: Playwright for JS-rendered pages (future enhancement)

### 5.5 Adapter: Documents

- Scans local directory for files matching `extensions`
- Extracts text: PDF (pymupdf), DOCX (python-docx), TXT/MD (direct read)
- Optionally copies originals to corpus `media/` directory
- Watches for new files on re-sync

---

## 6. Document Processing Pipeline

### 6.1 Pipeline Stages

```
Source Adapter → Text Extraction → Chunking → Embedding → Vector Store
     (fetch)        (clean)        (split)    (encode)     (upsert)
```

### 6.2 Text Extraction

Each content type has a dedicated extractor:

| Content Type | Extractor          | Library         |
|------------- |------------------- |---------------- |
| HTML         | HTMLToTextExtractor| BeautifulSoup   |
| PDF          | PDFExtractor       | pymupdf         |
| Plain text   | PassthroughExtractor | (none)        |
| Markdown     | MarkdownExtractor  | (strip markers) |
| Audio        | WhisperExtractor   | openai-whisper  |

### 6.3 Chunking

Configurable text chunking with these parameters:

- **chunk_size**: Target characters per chunk (default: 3200 ≈ 800 tokens)
- **chunk_overlap**: Characters of overlap between adjacent chunks (default: 400)
- **boundary_preference**: Break on paragraph boundaries (`\n\n`) when possible

The chunker outputs a list of `Chunk` objects:

```python
@dataclass
class Chunk:
    id: str                      # {document_id}:chunk{NNNN}
    text: str
    document_id: str
    chunk_index: int
    metadata: dict[str, Any]     # Inherited from document + chunk-specific
```

### 6.4 Embedding

- Default model: `sentence-transformers/all-mpnet-base-v2` (local, no API cost)
- ONNX backend preferred for CPU speedup; falls back to PyTorch
- Batch embedding for efficiency
- Model cached locally (configurable cache dir)

---

## 7. Vector Store

### 7.1 Interface

```python
class VectorStore(ABC):
    """Abstract interface for vector storage backends."""

    @abstractmethod
    def upsert(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        """Insert or update chunks with their embeddings."""

    @abstractmethod
    def search(self, query_embedding: list[float], n_results: int = 5,
               filters: dict | None = None) -> list[SearchResult]:
        """Search for similar chunks."""

    @abstractmethod
    def delete_document(self, document_id: str) -> None:
        """Remove all chunks for a document."""

    @abstractmethod
    def get_indexed_document_ids(self) -> set[str]:
        """Return IDs of all indexed documents (for incremental sync)."""

    @abstractmethod
    def collection_stats(self) -> dict[str, Any]:
        """Return statistics about the collection (chunk count, etc.)."""
```

### 7.2 ChromaDB Backend (Default)

- One collection per corpus (collection name = corpus slug)
- Cosine similarity (`hnsw:space: cosine`)
- Persisted to `{data_dir}/{corpus_slug}/vectordb/`
- Paginated retrieval for large collections (batches of 5,000)
- Metadata stored per chunk: document_id, chunk_index, source_type, title, url

### 7.3 Search Results

```python
@dataclass
class SearchResult:
    chunk_id: str
    document_id: str
    text: str
    similarity: float            # 0.0–1.0 (higher = more relevant)
    metadata: dict[str, Any]
```

---

## 8. CLI

### 8.1 Commands

```
archivist init                          # Create ~/.archivist/ with example config
archivist add <corpus-name>             # Interactive corpus creation wizard
archivist sync [corpus-name]            # Scrape + process + embed (all or one)
archivist search "query" [--corpus X]   # Semantic search across corpora
archivist status                        # Show corpora, source counts, last sync
archivist serve [--transport stdio|sse] # Start MCP server
archivist api [--host HOST] [--port N]  # Start REST API server
archivist export <corpus> <format>      # Export corpus data (json, csv)
```

### 8.2 Command Details

#### `archivist init`
- Creates `~/.archivist/` directory structure
- Writes default `config.yaml`
- Creates `corpora/` directory with an example YAML (commented out)
- Creates data directory if it doesn't exist

#### `archivist add <name>`
- Interactive wizard: prompts for source type, URL, options
- Writes a new corpus YAML to `~/.archivist/corpora/<name>.yaml`
- Validates configuration before saving

#### `archivist sync [name]`
- If name given: sync that corpus only
- If no name: sync all corpora
- Pipeline: discover → fetch (new only) → extract → chunk → embed → upsert
- Progress output with counts (new documents, chunks created)
- Idempotent: skips already-indexed documents

#### `archivist search "query" [--corpus X] [--n N]`
- Searches across all corpora (or specific one)
- Displays results with similarity score, document title, source, and excerpt
- Default: 5 results

#### `archivist status`
- Lists all configured corpora
- Shows per-corpus: source count, document count, chunk count, last sync time
- Shows data directory disk usage

#### `archivist serve`
- Starts MCP server (stdio by default, SSE optional)
- Exposes `search` tool for all corpora
- Tool parameters: query, corpus (optional), num_results

#### `archivist api`
- Starts FastAPI server
- Endpoints: search, list corpora, corpus status
- Bearer token auth when bound to non-localhost
- Disabled by default; opt-in via CLI flag

#### `archivist export <corpus> <format>`
- Exports corpus data to JSON or CSV
- Includes document metadata and chunk text
- Useful for migration or analysis

---

## 9. MCP Server

### 9.1 Tools

#### `search_corpus`
Search across one or all corpora.

**Parameters**:
- `query` (string, required): Search query
- `corpus` (string, optional): Limit to specific corpus
- `num_results` (integer, optional): 1–20, default 5

**Returns**: Formatted text with similarity scores, document titles, source URLs, and excerpts.

#### `list_corpora`
List all available corpora with basic stats.

**Returns**: Corpus names, descriptions, document counts.

#### `corpus_status`
Get detailed status for a specific corpus.

**Parameters**:
- `corpus` (string, required): Corpus slug

**Returns**: Sources, document count, chunk count, last sync, disk usage.

### 9.2 Transports

- **stdio** (default): For local Claude Code / Claude Desktop integration
- **SSE**: HTTP/SSE via Starlette + uvicorn for remote access

---

## 10. REST API

### 10.1 Endpoints

```
GET  /api/v1/corpora                          # List all corpora
GET  /api/v1/corpora/{slug}                   # Corpus details
GET  /api/v1/corpora/{slug}/documents         # List documents in corpus
POST /api/v1/search                           # Search (body: {query, corpus?, n?})
GET  /api/v1/health                           # Health check
```

### 10.2 Authentication

- **Localhost** (127.0.0.1): No auth required
- **Network-bound** (0.0.0.0): Bearer token required
- Token configured in `config.yaml` (never in repo)

### 10.3 Framework

- FastAPI with Pydantic models for request/response validation
- Uvicorn as ASGI server
- Optional: enabled only when user runs `archivist api`

---

## 11. Docker

### 11.1 Compose Services

```yaml
services:
  archivist:
    build: .
    volumes:
      - ./config:/root/.archivist    # Mount config
      - archivist-data:/data         # Persist data
    environment:
      - ARCHIVIST_DATA_DIR=/data
    command: serve --transport sse

  api:
    build: .
    ports:
      - "8090:8090"
    volumes:
      - ./config:/root/.archivist
      - archivist-data:/data
    environment:
      - ARCHIVIST_DATA_DIR=/data
      - ARCHIVIST_API_TOKEN=${ARCHIVIST_API_TOKEN}
    command: api --host 0.0.0.0 --port 8090

volumes:
  archivist-data:
```

### 11.2 Dockerfile

- Base: `python:3.12-slim`
- Multi-stage build: builder (compile deps) → runtime (slim image)
- Includes Whisper model download as optional build arg

---

## 12. Testing Strategy

### 12.1 Unit Tests

- Source adapter discovery and fetch logic (mocked HTTP)
- Text extractors (HTML, PDF, Markdown)
- Chunking algorithm (boundary detection, overlap, edge cases)
- Config loading and validation
- CLI command parsing

### 12.2 Integration Tests

- Full pipeline: config → discover → fetch → chunk → embed → search
- ChromaDB round-trip: upsert + search
- MCP server tool invocation
- REST API endpoints

### 12.3 Fixtures

- Sample RSS feeds (XML)
- Sample HTML pages
- Sample PDF documents
- Pre-built corpus configs

---

## 13. Error Handling

- **Network errors**: Retry with exponential backoff (3 attempts), then log and skip
- **Missing transcripts**: Log warning, skip document (don't fail entire sync)
- **Corrupt files**: Log error, skip, continue with remaining documents
- **Config errors**: Fail fast with clear error message and fix suggestion
- **Disk full**: Check available space before large operations, warn early

---

## 14. Tech Stack

| Component          | Library                        | Purpose                        |
|------------------- |------------------------------- |------------------------------- |
| CLI framework      | Click                          | Command-line interface         |
| HTTP client        | httpx                          | Async-capable HTTP requests    |
| HTML parsing       | BeautifulSoup4                 | HTML-to-text extraction        |
| PDF extraction     | pymupdf                        | PDF-to-text extraction         |
| RSS parsing        | feedparser                     | Podcast feed parsing           |
| Embeddings         | sentence-transformers          | Local embedding generation     |
| Vector store       | chromadb                       | Default vector database        |
| MCP server         | mcp                            | Model Context Protocol server  |
| REST API           | FastAPI + uvicorn              | Optional HTTP API              |
| Transcription      | openai-whisper                 | Audio-to-text (optional)       |
| Config             | PyYAML + Pydantic              | YAML loading + validation      |
| Testing            | pytest                         | Test framework                 |
| Type checking      | mypy (strict)                  | Static type analysis           |

---

## 15. Project Structure

```
archivist/
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
├── README.md
├── SPEC.md
├── LICENSE
├── .env.example
├── src/
│   └── archivist/
│       ├── __init__.py
│       ├── cli.py               # Click CLI entry point
│       ├── config.py            # Config loading and validation
│       ├── models.py            # Core data models
│       ├── pipeline.py          # Orchestrates discover → fetch → chunk → embed
│       ├── adapters/
│       │   ├── __init__.py
│       │   ├── base.py          # SourceAdapter ABC
│       │   ├── podcast.py       # Podcast/RSS adapter
│       │   ├── web.py           # Web scraping adapter
│       │   └── documents.py     # Local document adapter
│       ├── processors/
│       │   ├── __init__.py
│       │   ├── chunker.py       # Text chunking
│       │   ├── extractors.py    # Text extraction (HTML, PDF, MD, etc.)
│       │   └── whisper.py       # Whisper transcription
│       ├── stores/
│       │   ├── __init__.py
│       │   ├── base.py          # VectorStore ABC
│       │   └── chromadb.py      # ChromaDB implementation
│       ├── server/
│       │   ├── __init__.py
│       │   ├── mcp_server.py    # MCP server
│       │   └── api.py           # FastAPI REST API
│       └── utils/
│           ├── __init__.py
│           ├── http.py          # HTTP client with retry/delay
│           └── logging.py       # Logging setup
├── tests/
│   ├── conftest.py
│   ├── test_config.py
│   ├── test_chunker.py
│   ├── test_extractors.py
│   ├── test_podcast_adapter.py
│   ├── test_web_adapter.py
│   ├── test_document_adapter.py
│   ├── test_chromadb_store.py
│   ├── test_pipeline.py
│   ├── test_cli.py
│   ├── test_mcp_server.py
│   ├── test_api.py
│   └── fixtures/
│       ├── sample_feed.xml
│       ├── sample_page.html
│       ├── sample.pdf
│       └── sample_config.yaml
└── docs/
    └── examples/
        ├── podcast-corpus.yaml
        ├── web-corpus.yaml
        └── documents-corpus.yaml
```
