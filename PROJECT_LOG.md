# Archivist — Project Log

## 2026-03-18: Initial Implementation (v0.1.0)

### What was done
- Wrote full SPEC.md covering architecture, data models, source adapters, processing pipeline,
  vector store, CLI, MCP server, REST API, Docker packaging, and testing strategy
- Implemented complete project from scratch:
  - **Config system**: Pydantic-validated YAML config with global settings and per-corpus manifests
  - **Source adapters**: Podcast (RSS/feedparser), Web (BFS crawl with depth control), Documents (local files)
  - **Processors**: HTML/PDF/Markdown text extraction, paragraph-aware chunking with overlap
  - **Vector store**: ChromaDB backend with cosine similarity, paginated operations
  - **CLI**: Click-based CLI with init, add, sync, search, status, serve, api, export commands
  - **MCP server**: search_corpus, list_corpora, corpus_status tools over stdio/SSE
  - **REST API**: FastAPI with bearer token auth, search/list/status endpoints
  - **Docker**: Multi-stage Dockerfile, Docker Compose with MCP + API services
- 69 unit tests covering config, chunking, extractors, adapters, CLI
- Documentation: README.md, SPEC.md, example corpus configs

### Decisions made
- Used setuptools instead of hatchling (hatchling had compatibility issues with editable installs)
- Removed MIT License classifier from pyproject.toml (PEP 639 conflict with newer setuptools)
- sentence-transformers/all-mpnet-base-v2 as default embedding model (same as SNaI, proven quality)
- Paragraph-aware chunking at 3200 chars / 400 overlap (same parameters as SNaI)

### Problems encountered
- Hatchling build backend failed with `prepare_metadata_for_build_editable` error → switched to setuptools
- Setuptools rejected License classifier alongside `license = "MIT"` (PEP 639) → removed classifier
- Podcast adapter tests called feedparser.parse() inside mock context → moved parsing before patch

### Current state
- All 69 tests passing
- Project ready for initial public release
- No private data in codebase (verified: no emails, IPs, credentials, keychain references)

### Next steps
- End-to-end testing with real corpus (SNaI as first target)
- Whisper integration testing
- CI/CD setup (GitHub Actions)
- PyPI publishing
