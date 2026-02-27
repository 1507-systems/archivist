# Archivist

A generalized corpus-building tool — codifies the process pioneered in SNaI (podcast transcript
download → transcript processing → embedding for semantic search/RAG) so it can be reused across
future projects.

## Motivation

SNaI required a multi-step pipeline to build a searchable corpus from a podcast feed:
1. Define the source (RSS feed, YouTube channel, web archive, etc.)
2. Download/scrape the source content
3. Generate or fetch transcripts where needed
4. Clean and chunk the text
5. Generate embeddings and store in a vector store
6. Expose a search/RAG interface (MCP server, API, etc.)

Archivist should make this pipeline reproducible for any content source with minimal configuration.

## Goals

- Source adapters: podcast (RSS), YouTube, web pages, document collections
- Transcript generation: Whisper for audio, extraction for HTML/PDF
- Configurable chunking and overlap strategies
- Pluggable vector backends (local ChromaDB, Pinecone, CF Vectorize, etc.)
- Output: MCP server for semantic search + optional REST API
- CLI-first; Docker for deployment

## Relationship to SNaI

SNaI is the first use case. Once Archivist exists, the SNaI pipeline should be refactored to use it
as a dependency rather than maintaining its own ad hoc scripts.

## Status

**Design phase.** No code written yet. Begin implementation after SNaI embedding is unblocked.

## Tech Stack (Proposed)

- Python 3.12 (consistent with SNaI)
- Whisper (OpenAI) for audio transcription
- ChromaDB or CF Vectorize for embeddings
- FastAPI for the REST/MCP layer
- Docker for packaging

## Next Steps

1. Write SPEC.md with full requirements and architecture
2. Define source adapter interface (abstract base class)
3. Implement podcast/RSS adapter first (extract from SNaI's download-transcripts.sh)
4. Wire up to embedding pipeline
