"""CLI entry point for Archivist."""

from __future__ import annotations

import logging
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from archivist.config import (
    get_config_dir,
    get_data_dir,
    load_all_corpora,
    load_global_config,
    write_default_config,
)
from archivist.pipeline import sync_corpus
from archivist.utils.logging import setup_logging

logger = logging.getLogger(__name__)
console = Console()


@click.group()
@click.option("--config-dir", type=click.Path(path_type=Path), default=None,
              help="Override config directory (default: ~/.archivist/)")
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging")
@click.pass_context
def cli(ctx: click.Context, config_dir: Path | None, verbose: bool) -> None:
    """Archivist — build searchable corpora from any content source."""
    ctx.ensure_object(dict)
    ctx.obj["config_dir"] = config_dir or get_config_dir()
    ctx.obj["verbose"] = verbose

    # Load global config
    global_config = load_global_config(ctx.obj["config_dir"])
    ctx.obj["global_config"] = global_config

    # Setup logging
    log_level = "DEBUG" if verbose else global_config.logging.level
    setup_logging(level=log_level, log_file=global_config.logging.file)


@cli.command()
@click.pass_context
def init(ctx: click.Context) -> None:
    """Initialize Archivist config directory with default settings."""
    config_dir: Path = ctx.obj["config_dir"]
    if (config_dir / "config.yaml").exists():
        console.print(f"[yellow]Config already exists at {config_dir}[/yellow]")
        return

    write_default_config(config_dir)

    # Create data directory
    global_config = load_global_config(config_dir)
    data_dir = get_data_dir(global_config)
    data_dir.mkdir(parents=True, exist_ok=True)

    console.print(f"[green]Initialized Archivist at {config_dir}[/green]")
    console.print(f"  Config: {config_dir / 'config.yaml'}")
    console.print(f"  Data:   {data_dir}")
    console.print(f"  Corpora: {config_dir / 'corpora/'}")
    console.print("\nCreate a corpus config in corpora/ to get started.")


@cli.command()
@click.argument("name")
@click.pass_context
def add(ctx: click.Context, name: str) -> None:
    """Create a new corpus configuration interactively."""
    config_dir: Path = ctx.obj["config_dir"]
    corpora_dir = config_dir / "corpora"

    if not corpora_dir.exists():
        console.print("[red]Run 'archivist init' first.[/red]")
        raise SystemExit(1)

    corpus_path = corpora_dir / f"{name}.yaml"
    if corpus_path.exists():
        console.print(f"[red]Corpus '{name}' already exists at {corpus_path}[/red]")
        raise SystemExit(1)

    # Interactive prompts
    display_name = click.prompt("Display name", default=name.replace("-", " ").title())
    description = click.prompt("Description", default="")

    source_type = click.prompt(
        "Source type",
        type=click.Choice(["podcast", "web", "documents"]),
    )

    import yaml

    source: dict[str, object] = {"type": source_type}
    if source_type == "podcast":
        source["url"] = click.prompt("RSS feed URL")
        mode = click.prompt(
            "Transcript mode",
            type=click.Choice(["fetch", "whisper", "none"]),
            default="whisper",
        )
        source["transcript_mode"] = mode
        if mode == "fetch":
            source["transcript_url_pattern"] = click.prompt(
                "Transcript URL pattern (use {episode} placeholder)"
            )
        source["archive_media"] = click.confirm("Archive audio files?", default=False)
    elif source_type == "web":
        source["url"] = click.prompt("Starting URL")
        source["crawl_depth"] = click.prompt("Crawl depth", type=int, default=2)
    elif source_type == "documents":
        source["path"] = click.prompt("Document directory path")
        exts = click.prompt("File extensions (comma-separated)", default=".pdf,.txt,.md")
        source["extensions"] = [e.strip() for e in exts.split(",")]

    corpus_data = {
        "name": display_name,
        "description": description,
        "sources": [source],
    }

    with open(corpus_path, "w") as f:
        yaml.dump(corpus_data, f, default_flow_style=False, sort_keys=False)

    console.print(f"\n[green]Created corpus config: {corpus_path}[/green]")
    console.print(f"Run 'archivist sync {name}' to start building the corpus.")


@cli.command()
@click.argument("name", required=False)
@click.pass_context
def sync(ctx: click.Context, name: str | None) -> None:
    """Sync one or all corpora (discover, fetch, chunk, embed)."""
    config_dir: Path = ctx.obj["config_dir"]
    global_config = ctx.obj["global_config"]
    data_dir = get_data_dir(global_config)

    corpora = load_all_corpora(config_dir)
    if not corpora:
        console.print("[red]No corpora configured. Run 'archivist add <name>' first.[/red]")
        raise SystemExit(1)

    if name:
        if name not in corpora:
            console.print(f"[red]Corpus '{name}' not found. Available: {list(corpora.keys())}[/red]")
            raise SystemExit(1)
        targets = {name: corpora[name]}
    else:
        targets = corpora

    for slug, corpus_config in targets.items():
        console.print(f"\n[bold]Syncing corpus: {corpus_config.name}[/bold]")
        try:
            stats = sync_corpus(corpus_config, global_config, data_dir)
            console.print(
                f"  [green]Done:[/green] {stats['documents_fetched']} documents fetched, "
                f"{stats['chunks_created']} chunks created, "
                f"{stats['chunks_embedded']} chunks embedded"
            )
        except Exception as e:
            console.print(f"  [red]Error syncing {slug}: {e}[/red]")
            logger.exception("Failed to sync corpus %s", slug)


@cli.command()
@click.argument("query")
@click.option("--corpus", "-c", default=None, help="Limit search to specific corpus")
@click.option("--n", "-n", "num_results", default=5, help="Number of results (default: 5)")
@click.pass_context
def search(ctx: click.Context, query: str, corpus: str | None, num_results: int) -> None:
    """Search across corpora for semantically similar content."""
    config_dir: Path = ctx.obj["config_dir"]
    global_config = ctx.obj["global_config"]
    data_dir = get_data_dir(global_config)

    corpora = load_all_corpora(config_dir)
    if not corpora:
        console.print("[red]No corpora configured.[/red]")
        raise SystemExit(1)

    if corpus and corpus not in corpora:
        console.print(f"[red]Corpus '{corpus}' not found.[/red]")
        raise SystemExit(1)

    targets = {corpus: corpora[corpus]} if corpus else corpora

    # Lazy import to avoid loading ML models until needed
    from archivist.stores.chromadb import ChromaDBStore

    from sentence_transformers import SentenceTransformer

    model_name = global_config.defaults.embedding_model
    console.print(f"Loading embedding model: {model_name}...")
    model = SentenceTransformer(model_name)
    query_embedding = model.encode(query).tolist()

    all_results = []
    for slug, corpus_config in targets.items():
        store = ChromaDBStore(
            collection_name=slug,
            persist_dir=data_dir / slug / "vectordb",
        )
        results = store.search(query_embedding, n_results=num_results)
        for r in results:
            r.metadata["_corpus"] = slug
        all_results.extend(results)

    # Sort by similarity and take top N
    all_results.sort(key=lambda r: r.similarity, reverse=True)
    all_results = all_results[:num_results]

    if not all_results:
        console.print("[yellow]No results found.[/yellow]")
        return

    console.print(f"\n[bold]Search: '{query}'[/bold]")
    console.print(f"Found {len(all_results)} results\n")

    for i, result in enumerate(all_results, 1):
        corpus_name = result.metadata.get("_corpus", "unknown")
        title = result.metadata.get("title", "Untitled")
        url = result.metadata.get("url", "")
        console.print("=" * 60)
        console.print(
            f"[bold][Result {i}][/bold] {title} (corpus: {corpus_name}) "
            f"— similarity: {result.similarity:.3f}"
        )
        if url:
            console.print(f"  Source: {url}")
        console.print("─" * 40)
        # Truncate long excerpts for display
        excerpt = result.text[:500] + "..." if len(result.text) > 500 else result.text
        console.print(excerpt)

    console.print("=" * 60)


@cli.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show status of all configured corpora."""
    config_dir: Path = ctx.obj["config_dir"]
    global_config = ctx.obj["global_config"]
    data_dir = get_data_dir(global_config)

    corpora = load_all_corpora(config_dir)
    if not corpora:
        console.print("[yellow]No corpora configured. Run 'archivist add <name>' first.[/yellow]")
        return

    table = Table(title="Archivist Corpora")
    table.add_column("Corpus", style="bold")
    table.add_column("Sources")
    table.add_column("Documents")
    table.add_column("Chunks")
    table.add_column("Data Dir")

    for slug, corpus_config in corpora.items():
        corpus_data_dir = data_dir / slug
        # Count documents from transcripts dir
        transcripts_dir = corpus_data_dir / "transcripts"
        doc_count = len(list(transcripts_dir.glob("*"))) if transcripts_dir.exists() else 0

        # Get chunk count from vector store if available
        chunk_count = "—"
        vectordb_dir = corpus_data_dir / "vectordb"
        if vectordb_dir.exists():
            try:
                from archivist.stores.chromadb import ChromaDBStore
                store = ChromaDBStore(collection_name=slug, persist_dir=vectordb_dir)
                stats = store.collection_stats()
                chunk_count = str(stats.get("total_chunks", 0))
            except Exception:
                chunk_count = "error"

        table.add_row(
            f"{corpus_config.name}\n[dim]{slug}[/dim]",
            str(len(corpus_config.sources)),
            str(doc_count),
            chunk_count,
            str(corpus_data_dir) if corpus_data_dir.exists() else "[dim]not synced[/dim]",
        )

    console.print(table)
    console.print(f"\nConfig: {config_dir}")
    console.print(f"Data:   {data_dir}")


@cli.command()
@click.option("--transport", type=click.Choice(["stdio", "sse"]), default="stdio",
              help="MCP transport (default: stdio)")
@click.option("--host", default="127.0.0.1", help="SSE host (default: 127.0.0.1)")
@click.option("--port", default=8091, type=int, help="SSE port (default: 8091)")
@click.pass_context
def serve(ctx: click.Context, transport: str, host: str, port: int) -> None:
    """Start the MCP server for semantic search."""
    from archivist.server.mcp_server import run_mcp_server

    config_dir: Path = ctx.obj["config_dir"]
    global_config = ctx.obj["global_config"]
    data_dir = get_data_dir(global_config)

    console.print(f"Starting MCP server (transport: {transport})...")
    run_mcp_server(
        config_dir=config_dir,
        data_dir=data_dir,
        global_config=global_config,
        transport=transport,
        host=host,
        port=port,
    )


@cli.command()
@click.option("--host", default="127.0.0.1", help="API host (default: 127.0.0.1)")
@click.option("--port", default=8090, type=int, help="API port (default: 8090)")
@click.pass_context
def api(ctx: click.Context, host: str, port: int) -> None:
    """Start the REST API server."""
    from archivist.server.api import create_app

    import uvicorn

    config_dir: Path = ctx.obj["config_dir"]
    global_config = ctx.obj["global_config"]
    data_dir = get_data_dir(global_config)

    app = create_app(
        config_dir=config_dir,
        data_dir=data_dir,
        global_config=global_config,
    )

    console.print(f"Starting REST API at http://{host}:{port}")
    if host == "0.0.0.0":
        console.print("[yellow]Warning: Binding to all interfaces. Ensure ARCHIVIST_API_TOKEN is set.[/yellow]")

    uvicorn.run(app, host=host, port=port)


@cli.command()
@click.argument("corpus_name")
@click.argument("format", type=click.Choice(["json", "csv"]))
@click.option("--output", "-o", type=click.Path(path_type=Path), default=None,
              help="Output file path (default: stdout)")
@click.pass_context
def export(ctx: click.Context, corpus_name: str, format: str, output: Path | None) -> None:
    """Export corpus data to JSON or CSV."""
    import csv
    import json
    import sys

    config_dir: Path = ctx.obj["config_dir"]
    global_config = ctx.obj["global_config"]
    data_dir = get_data_dir(global_config)

    corpora = load_all_corpora(config_dir)
    if corpus_name not in corpora:
        console.print(f"[red]Corpus '{corpus_name}' not found.[/red]")
        raise SystemExit(1)

    from archivist.stores.chromadb import ChromaDBStore

    store = ChromaDBStore(
        collection_name=corpus_name,
        persist_dir=data_dir / corpus_name / "vectordb",
    )
    stats = store.collection_stats()
    total = stats.get("total_chunks", 0)
    if total == 0:
        console.print("[yellow]No data to export.[/yellow]")
        return

    # Fetch all chunks from the store
    all_data = store.get_all_chunks()

    if format == "json":
        export_data = [
            {
                "chunk_id": item["id"],
                "document_id": item["metadata"].get("document_id", ""),
                "text": item["text"],
                "metadata": item["metadata"],
            }
            for item in all_data
        ]
        out = json.dumps(export_data, indent=2)
        if output:
            output.write_text(out)
            console.print(f"[green]Exported {len(export_data)} chunks to {output}[/green]")
        else:
            sys.stdout.write(out)

    elif format == "csv":
        file = open(output, "w", newline="") if output else sys.stdout  # noqa: SIM115
        try:
            writer = csv.writer(file)
            writer.writerow(["chunk_id", "document_id", "title", "text"])
            for item in all_data:
                writer.writerow([
                    item["id"],
                    item["metadata"].get("document_id", ""),
                    item["metadata"].get("title", ""),
                    item["text"],
                ])
        finally:
            if output:
                file.close()
        if output:
            console.print(f"[green]Exported {len(all_data)} chunks to {output}[/green]")
