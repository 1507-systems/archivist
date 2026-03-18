"""HTTP client utilities with retry and polite delay."""

from __future__ import annotations

import logging
import time

import httpx

logger = logging.getLogger(__name__)

# Defaults
DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_BACKOFF = 2.0


def create_client(
    timeout: float = DEFAULT_TIMEOUT,
    follow_redirects: bool = True,
) -> httpx.Client:
    """Create an httpx client with sensible defaults."""
    return httpx.Client(
        timeout=timeout,
        follow_redirects=follow_redirects,
        headers={
            "User-Agent": "Archivist/0.1 (corpus-builder; +https://github.com/1507-systems/archivist)",
        },
    )


def fetch_with_retry(
    client: httpx.Client,
    url: str,
    *,
    max_retries: int = DEFAULT_MAX_RETRIES,
    backoff: float = DEFAULT_RETRY_BACKOFF,
    delay: float = 0.0,
) -> httpx.Response | None:
    """Fetch a URL with retry logic and optional delay.

    Returns the response on success (2xx), or None on 404.
    Raises httpx.HTTPStatusError for other error status codes after exhausting retries.
    """
    if delay > 0:
        time.sleep(delay)

    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            response = client.get(url)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError:
            # 404 already handled above; re-raise other HTTP errors on last attempt
            raise
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout) as e:
            last_error = e
            if attempt < max_retries - 1:
                wait = backoff * (2 ** attempt)
                logger.warning(
                    "Request to %s failed (attempt %d/%d): %s. Retrying in %.1fs",
                    url, attempt + 1, max_retries, e, wait,
                )
                time.sleep(wait)
            else:
                logger.error(
                    "Request to %s failed after %d attempts: %s",
                    url, max_retries, e,
                )

    if last_error:
        raise last_error
    # Should never reach here, but satisfies type checker
    msg = f"Failed to fetch {url} after {max_retries} attempts"
    raise RuntimeError(msg)
