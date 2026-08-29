"""Read the alarm time the phone pushed, with an on-disk cache and fallbacks.

The phone app (``phone_app/``) is the sole writer: it stores the chosen alarm
in a ``crdt_sync`` ``LogStore`` and pushes that log to a fixed path in the
private ``kuhyx/syncs`` repo. This module is the PC-side reader used by the
per-minute trigger (see ``_trigger.py``).

``shutdown-wrapper.sh`` no longer reads the remote file at all — it reads the
local cache this module writes, so there is only one remote reader to keep in
step (see ``CLAUDE.md``).

**Backends.** Firebase is preferred and GitHub is the cutover fallback, the
same order every other app in the fleet uses. Firebase needs ``crdt_sync``
(hence ``requests``), which is a real dependency declared in
``pyproject.toml``; the GitHub path stays stdlib-only (``urllib.request`` +
``json``) so that if the import is somehow missing on the production
interpreter, the alarm still resolves rather than crashing the trigger. That
is why the import below is guarded rather than top-level: this module runs
under ``/usr/bin/python``, not a venv, and a wake-up is not worth an
ImportError.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import logging
import sys
import time

from wake_alarm._alarm_payload import in_range
from wake_alarm._constants import (
    ALARM_CACHE_FILE,
    ALARM_CACHE_MAX_AGE_SECONDS,
    FALLBACK_ALARM_HOUR,
)
from wake_alarm._logging_setup import configure_logging
from wake_alarm._sync_transport import (
    _FIREBASE_AVAILABLE,
    _fetch_firebase_alarm,
    _fetch_github_alarm,
    _read_token,
    _read_token_fallback,
    fetch_remote_alarm,
)

# Re-imported under their original names: the suite patches
# `wake_alarm._sync._fetch_firebase_alarm` and friends, and a moved symbol
# makes patch() stop intercepting *silently*. __all__ stops ruff deleting
# them as unused.
__all__ = [
    "_FIREBASE_AVAILABLE",
    "Alarm",
    "_fetch_firebase_alarm",
    "_fetch_github_alarm",
    "_read_token",
    "_read_token_fallback",
    "fetch_remote_alarm",
    "get_alarm",
]

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Alarm:
    """A wall-clock alarm time, in the phone's (and the PC's) local timezone.

    Attributes:
        hour: Hour of day, 0-23.
        minute: Minute of hour, 0-59.
        source: Where the value came from ("remote", "cache", "stale-cache"
            or "fallback"). Purely informational — used for logging and the
            ``--show`` output so a wrong alarm is diagnosable at a glance.
    """

    hour: int
    minute: int
    source: str

    def __str__(self) -> str:
        """Render as ``HH:MM (source)``."""
        return f"{self.hour:02d}:{self.minute:02d} ({self.source})"


def _read_cache() -> tuple[int, int, float] | None:
    """Read the cached alarm.

    Returns:
        An (hour, minute, fetched_at) triple, or None if there is no usable
        cache.
    """
    try:
        with ALARM_CACHE_FILE.open() as handle:
            cached = json.load(handle)
    except OSError, json.JSONDecodeError:
        return None
    if not isinstance(cached, dict):
        return None
    hour = cached.get("hour")
    minute = cached.get("minute")
    fetched_at = cached.get("fetched_at")
    if not isinstance(hour, int) or not isinstance(minute, int):
        return None
    if not isinstance(fetched_at, (int, float)):
        return None
    if not in_range(hour, minute):
        return None
    return hour, minute, float(fetched_at)


def _write_cache(hour: int, minute: int) -> None:
    """Persist a freshly fetched alarm so later reads survive a network loss.

    Failures are logged and swallowed: an unwritable cache degrades the next
    read to a live fetch, which is not worth failing a trigger tick over.

    Args:
        hour: Hour of day, 0-23.
        minute: Minute of hour, 0-59.
    """
    entry = {"hour": hour, "minute": minute, "fetched_at": time.time()}
    try:
        ALARM_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with ALARM_CACHE_FILE.open("w") as handle:
            json.dump(entry, handle, indent=2)
    except OSError as exc:
        _logger.warning("Cannot write alarm cache: %s", exc)


def get_alarm(*, max_cache_age_seconds: float = ALARM_CACHE_MAX_AGE_SECONDS) -> Alarm:
    """Resolve the alarm to fire today, degrading gracefully at every step.

    Resolution order:

    1. A cache entry younger than *max_cache_age_seconds* (no network).
    2. A live fetch from GitHub (cached on success).
    3. Any cache entry, however stale — better an old alarm than none.
    4. ``FALLBACK_ALARM_HOUR:00``, if the alarm has never been read at all.

    Args:
        max_cache_age_seconds: How long a cached read is served without
            re-fetching. Injectable so tests and ``--show`` can force a live
            read.

    Returns:
        The resolved alarm. Always succeeds.
    """
    cached = _read_cache()
    if cached is not None:
        hour, minute, fetched_at = cached
        if time.time() - fetched_at < max_cache_age_seconds:
            return Alarm(hour, minute, "cache")

    remote = fetch_remote_alarm()
    if remote is not None:
        _write_cache(*remote)
        return Alarm(remote[0], remote[1], "remote")

    # Both degraded paths log at INFO for the same per-minute-tick reason as
    # _read_token above; _trigger warns when it fires on a degraded source.
    if cached is not None:
        _logger.info("Using stale cached alarm — sync read failed")
        return Alarm(cached[0], cached[1], "stale-cache")

    _logger.info(
        "No synced or cached alarm — falling back to %02d:00",
        FALLBACK_ALARM_HOUR,
    )
    return Alarm(FALLBACK_ALARM_HOUR, 0, "fallback")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse CLI arguments for the sync reader."""
    parser = argparse.ArgumentParser(
        description="Show the alarm time the phone last synced."
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Print the resolved alarm and where it came from.",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Ignore cache freshness and force a live fetch.",
    )
    return parser.parse_args(argv)


def main() -> None:
    """Entry point: print the resolved alarm (``--show`` is the only mode)."""
    configure_logging()
    args = _parse_args(sys.argv[1:])
    max_age = 0.0 if args.no_cache else ALARM_CACHE_MAX_AGE_SECONDS
    sys.stdout.write(f"{get_alarm(max_cache_age_seconds=max_age)}\n")


if __name__ == "__main__":
    main()
