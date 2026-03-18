"""Logging setup for Archivist."""

from __future__ import annotations

import logging
from pathlib import Path


def setup_logging(
    level: str = "INFO",
    log_file: str | None = None,
) -> None:
    """Configure logging for Archivist.

    Sets up a console handler (always) and an optional file handler.
    """
    root = logging.getLogger("archivist")
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Don't add handlers if they already exist (prevents duplicate output)
    if root.handlers:
        return

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)

    # File handler (optional)
    if log_file:
        log_path = Path(log_file).expanduser()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_path)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
