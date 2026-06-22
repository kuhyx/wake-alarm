"""Logging configuration for the wake_alarm entry point."""

from __future__ import annotations

import logging


def configure_logging() -> None:
    """Configure root logging with the standard daemon format and level."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
