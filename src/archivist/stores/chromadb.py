"""ChromaDB vector store backend."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import chromadb

from archivist.models import Chunk, SearchResult
from archivist.stores.base import VectorStore

logger = logging.getLogger(__name__)

# ChromaDB has a SQLite variable limit; paginate queries in batches
BATCH_SIZE = 5000


class ChromaDBStore(VectorStore):
    """ChromaDB-backed vector store with cosine similarity."""

    def __init__(self, collection_name: str, persist_dir: Path) -> None:
        self._collection_name = collection_name
        self._persist_dir = persist_dir
        persist_dir.mkdir(parents=True, exist_ok=True)

        self._client = chromadb.PersistentClient(path=str(persist_dir))
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def upsert(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        """Insert or update chunks with their embeddings in batches."""
        if not chunks:
            return

        for i in range(0, len(chunks), BATCH_SIZE):
            batch_chunks = chunks[i : i + BATCH_SIZE]
            batch_embeddings = embeddings[i : i + BATCH_SIZE]

            ids = [c.id for c in batch_chunks]
            documents = [c.text for c in batch_chunks]
            metadatas = [
                {
                    "document_id": c.document_id,
                    "chunk_index": c.chunk_index,
                    **c.metadata,
                }
                for c in batch_chunks
            ]

            self._collection.upsert(
                ids=ids,
                embeddings=batch_embeddings,  # type: ignore[arg-type]
                documents=documents,
                metadatas=metadatas,  # type: ignore[arg-type]
            )

        logger.info("Upserted %d chunks into collection '%s'", len(chunks), self._collection_name)

    def search(
        self,
        query_embedding: list[float],
        n_results: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Search for similar chunks using cosine similarity."""
        where = filters if filters else None
        results = self._collection.query(
            query_embeddings=[query_embedding],  # type: ignore[arg-type]
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        search_results: list[SearchResult] = []
        if not results["ids"] or not results["ids"][0]:
            return search_results

        for i, chunk_id in enumerate(results["ids"][0]):
            # ChromaDB returns cosine distance; convert to similarity (1 - distance)
            distance = results["distances"][0][i] if results["distances"] else 0.0
            similarity = 1.0 - distance

            raw_meta = results["metadatas"][0][i] if results["metadatas"] else {}
            metadata: dict[str, Any] = dict(raw_meta)
            document_id = str(metadata.get("document_id", ""))
            text = str(results["documents"][0][i]) if results["documents"] else ""

            search_results.append(
                SearchResult(
                    chunk_id=chunk_id,
                    document_id=document_id,
                    text=text,
                    similarity=similarity,
                    metadata=metadata,
                )
            )

        return search_results

    def delete_document(self, document_id: str) -> None:
        """Remove all chunks for a document."""
        self._collection.delete(where={"document_id": document_id})
        logger.info("Deleted chunks for document '%s'", document_id)

    def get_indexed_document_ids(self) -> set[str]:
        """Return IDs of all indexed documents via paginated retrieval."""
        document_ids: set[str] = set()
        total = self._collection.count()
        if total == 0:
            return document_ids

        offset = 0
        while offset < total:
            batch = self._collection.get(
                limit=BATCH_SIZE,
                offset=offset,
                include=["metadatas"],
            )
            if not batch["metadatas"]:
                break
            for meta in batch["metadatas"]:
                doc_id = meta.get("document_id")
                if doc_id:
                    document_ids.add(str(doc_id))
            offset += BATCH_SIZE

        return document_ids

    def collection_stats(self) -> dict[str, Any]:
        """Return statistics about the collection."""
        count = self._collection.count()
        return {
            "collection_name": self._collection_name,
            "total_chunks": count,
            "persist_dir": str(self._persist_dir),
        }

    def get_all_chunks(self) -> list[dict[str, Any]]:
        """Return all chunks with metadata for export."""
        total = self._collection.count()
        if total == 0:
            return []

        all_chunks: list[dict[str, Any]] = []
        offset = 0
        while offset < total:
            batch = self._collection.get(
                limit=BATCH_SIZE,
                offset=offset,
                include=["documents", "metadatas"],
            )
            for i, chunk_id in enumerate(batch["ids"]):
                all_chunks.append({
                    "id": chunk_id,
                    "text": batch["documents"][i] if batch["documents"] else "",
                    "metadata": batch["metadatas"][i] if batch["metadatas"] else {},
                })
            offset += BATCH_SIZE

        return all_chunks
