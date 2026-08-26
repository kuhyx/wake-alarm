"""Logging configuration for the wake_alarm entry points.

Two sinks, deliberately:

* **stderr -> journal** -- unchanged, human-readable, what ``journalctl`` shows.
* **JSONL file** -- machine-readable, greppable with ``jq``, so a failed
  wake-up can be reconstructed after the fact instead of re-debugged.

The JSONL handler carries a cross-process dedupe filter (see ``_log_dedupe``)
because ``_trigger`` runs as a fresh process every minute; without it, "log
everywhere" would mean 1440 identical lines a day.

Configuration never raises: a logging failure must not be the reason an alarm
does not go off.
"""

from __future__ import annotations

import logging

from wake_alarm._constants import LOG_DEDUPE_FILE, LOG_JSONL_FILE
from wake_alarm._log_dedupe import DedupeFilter
from wake_alarm._log_sink import build_handler

_STDERR_FORMAT = "%(asctime)s %(name)s %(levelname)s %(message)s"

# Marks the handler we own, so a second call is a no-op rather than a
# duplicate sink (main() runs once per process, but --demo and tests re-enter).
_HANDLER_FLAG = "_wake_alarm_jsonl"


def _already_attached(root: logging.Logger) -> bool:
    """Report whether the JSONL handler is already installed.

    Args:
        root: The root logger to inspect.

    Returns:
        True if a previous call already attached the handler.
    """
    return any(getattr(h, _HANDLER_FLAG, False) for h in root.handlers)


def configure_logging(*, component: str = "wake_alarm") -> None:
    """Configure the daemon log format plus the structured JSONL sink.

    Args:
        component: Name recorded on every JSONL record, identifying which
            entry point emitted it (``alarm``, ``trigger``, ``sync``).
    """
    logging.basicConfig(level=logging.INFO, format=_STDERR_FORMAT)
    root = logging.getLogger()
    if _already_attached(root):
        return
    try:
        handler = build_handler(LOG_JSONL_FILE)
    except OSError:
        # No structured log is survivable; a crash here is not.
        logging.getLogger(__name__).info(
            "structured log unavailable; journal only",
        )
        return
    handler.addFilter(DedupeFilter(LOG_DEDUPE_FILE))
    handler.addFilter(_ComponentFilter(component))
    setattr(handler, _HANDLER_FLAG, True)
    root.addHandler(handler)


class _ComponentFilter(logging.Filter):
    """Stamp every record with the entry point that produced it."""

    def __init__(self, component: str) -> None:
        """Initialise the filter.

        Args:
            component: Value to set on each record.
        """
        super().__init__()
        self._component = component

    def filter(self, record: logging.LogRecord) -> bool:
        """Attach the component name to *record*.

        Args:
            record: The record being emitted.

        Returns:
            Always True; this filter annotates rather than excludes.
        """
        record.component = self._component
        return True
