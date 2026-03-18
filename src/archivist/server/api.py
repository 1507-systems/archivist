"""FastAPI REST API for Archivist."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from archivist.config import GlobalConfig, load_all_corpora
from archivist.stores.chromadb import ChromaDBStore

# -- Request/Response models --

class SearchRequest(BaseModel):
    """Search request body."""

    query: str
    corpus: str | None = None
    n: int = Field(default=5, ge=1, le=20)


class SearchResultItem(BaseModel):
    """A single search result."""

    chunk_id: str
    document_id: str
    text: str
    similarity: float
    metadata: dict[str, Any]


class SearchResponse(BaseModel):
    """Search response."""

    query: str
    results: list[SearchResultItem]


class CorpusSummary(BaseModel):
    """Summary of a corpus."""

    slug: str
    name: str
    description: str
    source_count: int
    chunk_count: int


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    version: str
    corpora_count: int


# -- App factory --

def create_app(
    config_dir: Path,
    data_dir: Path,
    global_config: GlobalConfig,
) -> FastAPI:
    """Create the FastAPI application with corpus search endpoints."""
    app = FastAPI(
        title="Archivist API",
        description="Semantic search across Archivist corpora",
        version="0.1.0",
    )

    # Store config in app state for dependency injection
    app.state.config_dir = config_dir
    app.state.data_dir = data_dir
    app.state.global_config = global_config

    # Bearer token auth (required when binding to non-localhost)
    api_token = os.environ.get("ARCHIVIST_API_TOKEN")

    async def verify_auth(request: Request) -> None:
        """Verify bearer token if one is configured."""
        if not api_token:
            return
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing bearer token")
        if auth[7:] != api_token:
            raise HTTPException(status_code=403, detail="Invalid bearer token")

    @app.get("/api/v1/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        corpora = load_all_corpora(config_dir)
        return HealthResponse(
            status="ok",
            version="0.1.0",
            corpora_count=len(corpora),
        )

    @app.get("/api/v1/corpora", response_model=list[CorpusSummary],
             dependencies=[Depends(verify_auth)])
    async def list_corpora() -> list[CorpusSummary]:
        corpora = load_all_corpora(config_dir)
        summaries: list[CorpusSummary] = []
        for slug, config in corpora.items():
            chunk_count = 0
            vectordb_dir = data_dir / slug / "vectordb"
            if vectordb_dir.exists():
                try:
                    store = ChromaDBStore(collection_name=slug, persist_dir=vectordb_dir)
                    stats = store.collection_stats()
                    chunk_count = stats.get("total_chunks", 0)
                except Exception:
                    pass
            summaries.append(CorpusSummary(
                slug=slug,
                name=config.name,
                description=config.description,
                source_count=len(config.sources),
                chunk_count=chunk_count,
            ))
        return summaries

    @app.get("/api/v1/corpora/{slug}", response_model=CorpusSummary,
             dependencies=[Depends(verify_auth)])
    async def get_corpus(slug: str) -> CorpusSummary:
        corpora = load_all_corpora(config_dir)
        if slug not in corpora:
            raise HTTPException(status_code=404, detail=f"Corpus '{slug}' not found")
        config = corpora[slug]
        chunk_count = 0
        vectordb_dir = data_dir / slug / "vectordb"
        if vectordb_dir.exists():
            try:
                store = ChromaDBStore(collection_name=slug, persist_dir=vectordb_dir)
                stats = store.collection_stats()
                chunk_count = stats.get("total_chunks", 0)
            except Exception:
                pass
        return CorpusSummary(
            slug=slug,
            name=config.name,
            description=config.description,
            source_count=len(config.sources),
            chunk_count=chunk_count,
        )

    @app.post("/api/v1/search", response_model=SearchResponse,
              dependencies=[Depends(verify_auth)])
    async def search_corpora(req: SearchRequest) -> SearchResponse:
        if not req.query.strip():
            raise HTTPException(status_code=400, detail="Query cannot be empty")

        corpora = load_all_corpora(config_dir)
        if req.corpus and req.corpus not in corpora:
            raise HTTPException(status_code=404, detail=f"Corpus '{req.corpus}' not found")

        targets = {req.corpus: corpora[req.corpus]} if req.corpus else corpora

        # Load model and generate query embedding
        from sentence_transformers import SentenceTransformer
        model_name = global_config.defaults.embedding_model
        model = SentenceTransformer(model_name)
        query_embedding = model.encode(req.query).tolist()

        all_results = []
        for slug in targets:
            vectordb_dir = data_dir / slug / "vectordb"
            if not vectordb_dir.exists():
                continue
            store = ChromaDBStore(collection_name=slug, persist_dir=vectordb_dir)
            results = store.search(query_embedding, n_results=req.n)
            for r in results:
                r.metadata["_corpus"] = slug
            all_results.extend(results)

        all_results.sort(key=lambda r: r.similarity, reverse=True)
        all_results = all_results[: req.n]

        return SearchResponse(
            query=req.query,
            results=[
                SearchResultItem(
                    chunk_id=r.chunk_id,
                    document_id=r.document_id,
                    text=r.text,
                    similarity=r.similarity,
                    metadata=r.metadata,
                )
                for r in all_results
            ],
        )

    return app
