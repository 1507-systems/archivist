"""Corpus sync pipeline — orchestrates discover → fetch → chunk → embed."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from archivist.adapters import get_adapter
from archivist.config import CorpusConfig, GlobalConfig, SourceConfig
from archivist.models import Chunk, DocumentContent
from archivist.processors.chunker import chunk_text
from archivist.stores.chromadb import ChromaDBStore

logger = logging.getLogger(__name__)


def sync_corpus(
    corpus_config: CorpusConfig,
    global_config: GlobalConfig,
    data_dir: Path,
) -> dict[str, Any]:
    """Run the full sync pipeline for a corpus.

    Pipeline stages:
    1. Discover: find all documents from all sources
    2. Filter: skip already-indexed documents (incremental sync)
    3. Fetch: download/extract text for new documents
    4. Chunk: split text into overlapping chunks
    5. Embed: generate embeddings for chunks
    6. Upsert: store embeddings in vector store

    Returns:
        Statistics dict with counts of documents and chunks processed.
    """
    slug = corpus_config.slug or "unknown"
    defaults = global_config.defaults

    chunk_size = corpus_config.effective_chunk_size(defaults)
    chunk_overlap = corpus_config.effective_chunk_overlap(defaults)
    embedding_model = corpus_config.effective_embedding_model(defaults)

    # Initialize vector store
    vectordb_dir = data_dir / slug / "vectordb"
    store = ChromaDBStore(collection_name=slug, persist_dir=vectordb_dir)

    # Get already-indexed document IDs for incremental sync
    indexed_ids = store.get_indexed_document_ids()
    logger.info("Found %d already-indexed documents in '%s'", len(indexed_ids), slug)

    # Track stats
    stats: dict[str, Any] = {
        "documents_discovered": 0,
        "documents_skipped": 0,
        "documents_fetched": 0,
        "documents_failed": 0,
        "chunks_created": 0,
        "chunks_embedded": 0,
    }

    # Collect all new documents and their chunks across all sources
    all_chunks: list[Chunk] = []

    for source_index, source_config in enumerate(corpus_config.sources):
        logger.info(
            "Processing source %d/%d (type: %s)",
            source_index + 1,
            len(corpus_config.sources),
            source_config.type,
        )

        adapter_cls = get_adapter(source_config.type)
        adapter = adapter_cls(
            source_config=source_config,
            corpus_slug=slug,
            data_dir=data_dir,
        )

        # Discover
        try:
            documents = adapter.discover()
        except Exception as e:
            logger.error("Failed to discover documents from source %d: %s", source_index, e)
            continue

        stats["documents_discovered"] += len(documents)

        # Filter already-indexed
        new_documents = [d for d in documents if d.id not in indexed_ids]
        stats["documents_skipped"] += len(documents) - len(new_documents)

        if not new_documents:
            logger.info("No new documents to process for source %d", source_index)
            continue

        logger.info("Fetching %d new documents (skipping %d already indexed)",
                     len(new_documents), len(documents) - len(new_documents))

        # Fetch and chunk each new document
        for doc_meta in new_documents:
            try:
                content = adapter.fetch(doc_meta)
            except Exception as e:
                logger.error("Failed to fetch document %s: %s", doc_meta.id, e)
                stats["documents_failed"] += 1
                continue

            if not content.text.strip():
                logger.warning("Empty content for document %s, skipping", doc_meta.id)
                stats["documents_failed"] += 1
                continue

            stats["documents_fetched"] += 1

            # Build chunk metadata from document
            chunk_metadata = {
                "title": doc_meta.title,
                "url": doc_meta.url or "",
                "content_type": content.content_type,
                **{k: v for k, v in doc_meta.metadata.items()
                   if isinstance(v, (str, int, float, bool))},
            }

            chunks = chunk_text(
                text=content.text,
                document_id=doc_meta.id,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                metadata=chunk_metadata,
            )
            stats["chunks_created"] += len(chunks)
            all_chunks.extend(chunks)

    # Embed and upsert all chunks
    if all_chunks:
        logger.info("Embedding %d chunks with model '%s'...", len(all_chunks), embedding_model)
        embeddings = _generate_embeddings(
            [c.text for c in all_chunks],
            model_name=embedding_model,
        )
        stats["chunks_embedded"] = len(embeddings)

        store.upsert(all_chunks, embeddings)
        logger.info("Pipeline complete for '%s': %s", slug, stats)
    else:
        logger.info("No new chunks to embed for '%s'", slug)

    return stats


def _generate_embeddings(
    texts: list[str],
    model_name: str = "all-mpnet-base-v2",
) -> list[list[float]]:
    """Generate embeddings for a list of texts using sentence-transformers."""
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(model_name)
    embeddings = model.encode(texts, show_progress_bar=True)
    return embeddings.tolist()
