"""Source adapters for fetching content from various origins."""

from archivist.adapters.base import SourceAdapter
from archivist.adapters.documents import DocumentAdapter
from archivist.adapters.podcast import PodcastAdapter
from archivist.adapters.web import WebAdapter

ADAPTER_REGISTRY: dict[str, type[SourceAdapter]] = {
    "podcast": PodcastAdapter,
    "web": WebAdapter,
    "documents": DocumentAdapter,
}


def get_adapter(source_type: str) -> type[SourceAdapter]:
    """Return the adapter class for the given source type."""
    if source_type not in ADAPTER_REGISTRY:
        msg = f"Unknown source type: '{source_type}'. Available: {list(ADAPTER_REGISTRY.keys())}"
        raise ValueError(msg)
    return ADAPTER_REGISTRY[source_type]


__all__ = [
    "ADAPTER_REGISTRY",
    "DocumentAdapter",
    "PodcastAdapter",
    "SourceAdapter",
    "WebAdapter",
    "get_adapter",
]
