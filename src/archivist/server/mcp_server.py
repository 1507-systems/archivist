"""MCP server for Archivist — exposes corpus search via Model Context Protocol."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from archivist.config import GlobalConfig, load_all_corpora
from archivist.stores.chromadb import ChromaDBStore

logger = logging.getLogger(__name__)

MAX_RESULTS = 20

# Lazy-loaded singletons to avoid loading ML models on import
_model: Any = None
_stores: dict[str, ChromaDBStore] = {}


def _get_model(model_name: str) -> Any:
    """Lazy-load the sentence-transformers model."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(model_name)
    return _model


def _get_stores(
    config_dir: Path,
    data_dir: Path,
) -> dict[str, ChromaDBStore]:
    """Initialize ChromaDB stores for all configured corpora."""
    global _stores
    if not _stores:
        corpora = load_all_corpora(config_dir)
        for slug in corpora:
            vectordb_dir = data_dir / slug / "vectordb"
            if vectordb_dir.exists():
                _stores[slug] = ChromaDBStore(
                    collection_name=slug,
                    persist_dir=vectordb_dir,
                )
    return _stores


def run_mcp_server(
    config_dir: Path,
    data_dir: Path,
    global_config: GlobalConfig,
    transport: str = "stdio",
    host: str = "127.0.0.1",
    port: int = 8091,
) -> None:
    """Start the MCP server with configured tools."""
    import asyncio

    server = Server("archivist")
    model_name = global_config.defaults.embedding_model
    corpora = load_all_corpora(config_dir)

    @server.list_tools()  # type: ignore[no-untyped-call,untyped-decorator]
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="search_corpus",
                description=(
                    "Search across Archivist corpora for semantically similar content. "
                    f"Available corpora: {', '.join(corpora.keys()) or 'none configured'}"
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query",
                        },
                        "corpus": {
                            "type": "string",
                            "description": "Optional: limit search to specific corpus",
                        },
                        "num_results": {
                            "type": "integer",
                            "description": "Number of results (1-20, default 5)",
                            "minimum": 1,
                            "maximum": MAX_RESULTS,
                            "default": 5,
                        },
                    },
                    "required": ["query"],
                },
            ),
            Tool(
                name="list_corpora",
                description="List all available Archivist corpora with basic stats",
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
            Tool(
                name="corpus_status",
                description="Get detailed status for a specific corpus",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "corpus": {
                            "type": "string",
                            "description": "Corpus slug",
                        },
                    },
                    "required": ["corpus"],
                },
            ),
        ]

    @server.call_tool()  # type: ignore[untyped-decorator]
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        if name == "search_corpus":
            return _handle_search(arguments, config_dir, data_dir, model_name)
        elif name == "list_corpora":
            return _handle_list_corpora(config_dir, data_dir)
        elif name == "corpus_status":
            return _handle_corpus_status(arguments, config_dir, data_dir)
        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    if transport == "stdio":
        asyncio.run(_run_stdio(server))
    elif transport == "sse":
        _run_sse(server, host, port)


async def _run_stdio(server: Server) -> None:
    """Run the MCP server over stdio."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def _run_sse(server: Server, host: str, port: int) -> None:
    """Run the MCP server over SSE (HTTP)."""
    import uvicorn
    from mcp.server.sse import SseServerTransport
    from starlette.applications import Starlette
    from starlette.routing import Route

    sse = SseServerTransport("/messages/")

    async def handle_sse(request: Any) -> Any:
        async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
            await server.run(streams[0], streams[1], server.create_initialization_options())

    app = Starlette(routes=[
        Route("/sse", endpoint=handle_sse),
        Route("/messages/", endpoint=sse.handle_post_message, methods=["POST"]),
    ])

    uvicorn.run(app, host=host, port=port)


def _handle_search(
    arguments: dict[str, Any],
    config_dir: Path,
    data_dir: Path,
    model_name: str,
) -> list[TextContent]:
    """Handle the search_corpus tool call."""
    query = arguments.get("query", "").strip()
    if not query:
        return [TextContent(type="text", text="Error: query cannot be empty")]

    corpus_filter = arguments.get("corpus")
    num_results = min(arguments.get("num_results", 5), MAX_RESULTS)

    model = _get_model(model_name)
    stores = _get_stores(config_dir, data_dir)

    if corpus_filter:
        if corpus_filter not in stores:
            return [TextContent(
                type="text",
                text=f"Corpus '{corpus_filter}' not found. Available: {list(stores.keys())}",
            )]
        target_stores = {corpus_filter: stores[corpus_filter]}
    else:
        target_stores = stores

    if not target_stores:
        return [TextContent(type="text", text="No corpora available. Run 'archivist sync' first.")]

    query_embedding = model.encode(query).tolist()

    all_results = []
    for slug, store in target_stores.items():
        results = store.search(query_embedding, n_results=num_results)
        for r in results:
            r.metadata["_corpus"] = slug
        all_results.extend(results)

    all_results.sort(key=lambda r: r.similarity, reverse=True)
    all_results = all_results[:num_results]

    if not all_results:
        return [TextContent(type="text", text=f"No results found for: '{query}'")]

    # Format output
    lines = [f"Archivist search: '{query}'", f"Returned {len(all_results)} results", ""]
    for i, result in enumerate(all_results, 1):
        corpus_name = result.metadata.get("_corpus", "unknown")
        title = result.metadata.get("title", "Untitled")
        url = result.metadata.get("url", "")
        lines.append("=" * 60)
        lines.append(
            f"[Result {i}] {title} (corpus: {corpus_name}) "
            f"— similarity: {result.similarity:.3f}"
        )
        if url:
            lines.append(f"Source: {url}")
        lines.append("─" * 40)
        excerpt = result.text[:600] + "..." if len(result.text) > 600 else result.text
        lines.append(excerpt)

    lines.append("=" * 60)
    return [TextContent(type="text", text="\n".join(lines))]


def _handle_list_corpora(
    config_dir: Path,
    data_dir: Path,
) -> list[TextContent]:
    """Handle the list_corpora tool call."""
    corpora = load_all_corpora(config_dir)
    if not corpora:
        return [TextContent(type="text", text="No corpora configured.")]

    lines = ["Available corpora:", ""]
    for slug, config in corpora.items():
        vectordb_dir = data_dir / slug / "vectordb"
        chunks = "not synced"
        if vectordb_dir.exists():
            try:
                store = ChromaDBStore(collection_name=slug, persist_dir=vectordb_dir)
                stats = store.collection_stats()
                chunks = f"{stats['total_chunks']} chunks"
            except Exception:
                chunks = "error"
        lines.append(f"  {slug}: {config.name} ({len(config.sources)} sources, {chunks})")
        if config.description:
            lines.append(f"    {config.description}")

    return [TextContent(type="text", text="\n".join(lines))]


def _handle_corpus_status(
    arguments: dict[str, Any],
    config_dir: Path,
    data_dir: Path,
) -> list[TextContent]:
    """Handle the corpus_status tool call."""
    slug = arguments.get("corpus", "")
    corpora = load_all_corpora(config_dir)

    if slug not in corpora:
        return [TextContent(
            type="text",
            text=f"Corpus '{slug}' not found. Available: {list(corpora.keys())}",
        )]

    config = corpora[slug]
    corpus_data_dir = data_dir / slug
    lines = [
        f"Corpus: {config.name} ({slug})",
        f"Description: {config.description or '(none)'}",
        f"Sources: {len(config.sources)}",
    ]

    for i, source in enumerate(config.sources):
        lines.append(f"  [{i}] type={source.type} url={source.url or source.path or 'N/A'}")

    vectordb_dir = corpus_data_dir / "vectordb"
    if vectordb_dir.exists():
        try:
            store = ChromaDBStore(collection_name=slug, persist_dir=vectordb_dir)
            stats = store.collection_stats()
            lines.append(f"Chunks: {stats['total_chunks']}")
        except Exception as e:
            lines.append(f"Vector store error: {e}")
    else:
        lines.append("Status: not synced yet")

    return [TextContent(type="text", text="\n".join(lines))]
