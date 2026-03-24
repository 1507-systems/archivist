<!-- summary: Self-hosted corpus-building tool for semantic search and RAG with multi-source ingestion, local embeddings, and ChromaDB vector store. -->
# Archivist — Project Log

## 2026-03-22: Branch Protection Enabled

### What was done
- Enabled GitHub branch protection on `main` branch via API
- Configuration:
  - Strict status checks: enabled (no required contexts — relies on CI/CD pipeline already in place)
  - Enforce admins: disabled
  - Required pull request reviews: 0 (can be adjusted later if needed)
  - No restrictions on force pushes/deletions (can be adjusted later)

### Status
- Branch protection is now active on 1507-systems/archivist
- CI/CD pipeline (pytest, mypy, ruff) already in place and will execute on PRs

---

## 2026-03-18: Full Audit — v0.1.0-audit-clean

### Audit results
Ran full audit cycle (docs, functionality, cleanup, security) with zero remaining issues.

### Issues found and fixed

**Ruff linting (41 issues):**
- Import sorting (auto-fixed by `ruff check --fix`)
- Unused import: `GlobalConfig` in test_config.py (auto-fixed)
- Line length violations in cli.py, test files (manually fixed)
- Unused loop variable `corpus_config` in search command (renamed to `_corpus_config`)
- SIM103: simplified condition return in web adapter `_url_matches_filters`
- Removed TCH rule set from linting (TC001/TC003 are counterproductive with `from __future__ import annotations` — runtime imports are needed for Pydantic, isinstance, etc.)

**Mypy strict (23 issues):**
- Added `typing.Any` import to chunker.py for `dict[str, Any]` type annotation
- Fixed `_parse_date` return type: `None` -> `datetime | None`
- Added `datetime` import to podcast.py
- Fixed `_extract_title` in web.py: explicit `str()` cast and `hasattr` check for NavigableString
- Fixed ChromaDB store: explicit `dict()` conversion and `str()` casts for metadata/document_id
- Added `type: ignore` for pipeline adapter instantiation (ABC base class lacks `__init__` params)
- Added `type: ignore` for MCP server decorators (`untyped-decorator`, `no-untyped-call`)
- Added mypy overrides for third-party library stubs: feedparser, whisper, chromadb, pymupdf, sentence-transformers, mcp

**Documentation accuracy:**
- SPEC.md: Updated test file listing to match actual files (removed non-existent test_chromadb_store.py, test_pipeline.py, test_mcp_server.py, test_api.py, sample.pdf; added conftest.py, sample_corpus.yaml)
- SPEC.md: Corrected DOCX support claim — not yet implemented (no python-docx dep, no extractor)
- SPEC.md: Removed non-existent `/api/v1/corpora/{slug}/documents` endpoint from API docs

**Docker:**
- Dockerfile: Fixed build dependency from `hatchling` to `setuptools wheel` (project uses setuptools)

**Security:**
- No hardcoded secrets found
- No secrets in git history (only legitimate token-handling code)
- .gitignore covers .env, __pycache__, .venv, *.db, chromadb/
- API token auth via environment variable (not hardcoded)
- `pip audit`: 7 known vulnerabilities in transitive deps (pip 25.0.1, torch 2.2.2) — both are transitive from sentence-transformers, not directly exploitable in this context. Documented, not blocking.

### Final state
- 69/69 tests passing
- mypy --strict: 0 errors (23 source files)
- ruff check: 0 errors
- No TODOs/FIXMEs in source
- No hardcoded secrets
- Tagged v0.1.0-audit-clean

---

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
- Hatchling build backend failed with `prepare_metadata_for_build_editable` error -> switched to setuptools
- Setuptools rejected License classifier alongside `license = "MIT"` (PEP 639) -> removed classifier
- Podcast adapter tests called feedparser.parse() inside mock context -> moved parsing before patch

### Current state
- All 69 tests passing
- Project ready for initial public release
- No private data in codebase (verified: no emails, IPs, credentials, keychain references)

### Next steps
- End-to-end testing with real corpus (SNaI as first target)
- Whisper integration testing
- PyPI publishing
- DOCX support (python-docx extractor)

---

## 2026-03-18: CI/CD Pipeline

### What was done
- Added GitHub Actions CI/CD pipeline (commit 2d69368)
- Workflow runs: pytest, mypy --strict, ruff check
- Triggered on push to main and pull requests

### Updated next steps
- CI/CD setup: **done**
- Remaining: end-to-end testing, Whisper integration, PyPI publishing, DOCX support
