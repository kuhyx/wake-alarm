"""JSONL log sink: machine-readable events alongside the human journal.

The journal (stderr -> systemd) stays exactly as it was; this is *additive*.
Every record is one JSON object on one line, so a failed wake-up can be
reconstructed with ``jq`` instead of re-derived by hand:

    jq 'select(.corr == "wake-20260826-0700")' ~/.local/state/wake_alarm/events.jsonl

Extra keyword arguments passed to a logging call via ``extra={"fields": {...}}``
are merged into the record, so callers add structure without a bespoke API.
"""

from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

# Attribute names ``logging`` sets on every record; anything else in __dict__
# came from the caller's ``extra=`` and belongs in the payload.
_RESERVED = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    },
)

MAX_BYTES = 5 * 1024 * 1024
BACKUP_COUNT = 5


class JsonlFormatter(logging.Formatter):
    """Render a log record as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        """Serialise *record* as compact JSON.

        Args:
            record: The record to render.

        Returns:
            One line of JSON, no trailing newline.
        """
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        payload.update(
            {
                key: value
                for key, value in record.__dict__.items()
                if key not in _RESERVED and not key.startswith("_")
            },
        )
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=repr, sort_keys=True)


def build_handler(path: Path) -> RotatingFileHandler:
    """Create the rotating JSONL handler writing to *path*.

    Args:
        path: Destination file; its parent is created if absent.

    Returns:
        A configured handler, ready to attach to the root logger.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        path,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setFormatter(JsonlFormatter())
    return handler
