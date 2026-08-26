"""Suppress consecutive identical events across *separate processes*.

``_trigger`` is a fresh process every 60 seconds, so an in-memory rate limiter
would reset on every tick and suppress nothing. The fingerprint of the last
emitted event therefore lives on disk.

This is what lets the routine paths log at all without producing 1440 identical
journal lines a day, and it satisfies the standing "do not raise the level of
_sync's degraded-read paths" rule *by construction* rather than by keeping
levels artificially low. When a run of duplicates finally breaks, the next
distinct record carries ``suppressed_repeats`` so nothing is silently lost.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

# Records carrying this attribute participate in dedupe; others always pass.
DEDUPE_ATTR = "dedupe_key"
REPEATS_FIELD = "suppressed_repeats"


def _fingerprint(key: str, level: int) -> str:
    """Hash the dedupe key and level into a short stable digest.

    Args:
        key: Caller-supplied dedupe key.
        level: Numeric log level.

    Returns:
        A hex digest identifying this event shape.
    """
    return hashlib.sha256(f"{level}:{key}".encode()).hexdigest()[:16]


class DedupeFilter(logging.Filter):
    """Drop a record whose dedupe key matches the previously emitted one."""

    def __init__(self, state_file: Path) -> None:
        """Initialise the filter.

        Args:
            state_file: Where the last-emitted fingerprint is persisted.
        """
        super().__init__()
        self._state_file = state_file

    def _read(self) -> tuple[str, int]:
        """Read the stored fingerprint and repeat count.

        Returns:
            The fingerprint and how many duplicates have been suppressed.
        """
        try:
            raw = json.loads(self._state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return "", 0
        if not isinstance(raw, dict):
            return "", 0
        digest = raw.get("digest")
        count = raw.get("count")
        if not isinstance(digest, str) or not isinstance(count, int):
            return "", 0
        return digest, count

    def _write(self, digest: str, count: int) -> None:
        """Persist the fingerprint and repeat count, ignoring IO errors.

        Args:
            digest: Fingerprint of the last emitted record.
            count: Number of duplicates suppressed since it was emitted.
        """
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            self._state_file.write_text(
                json.dumps({"digest": digest, "count": count}),
                encoding="utf-8",
            )
        except OSError:
            # Logging must never be the thing that breaks the alarm.
            pass

    def filter(self, record: logging.LogRecord) -> bool:
        """Decide whether *record* should be emitted.

        Args:
            record: The candidate record.

        Returns:
            True to emit, False to suppress as a duplicate.
        """
        key = getattr(record, DEDUPE_ATTR, None)
        if not isinstance(key, str):
            return True
        digest = _fingerprint(key, record.levelno)
        previous, count = self._read()
        if digest == previous:
            self._write(digest, count + 1)
            return False
        if count:
            setattr(record, REPEATS_FIELD, count)
        self._write(digest, 0)
        return True
