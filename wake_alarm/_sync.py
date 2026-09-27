"""Read the alarm time the phone pushed, with an on-disk cache and fallbacks.

The phone app (``phone_app/``) is the sole writer: it stores the chosen alarm
in a ``crdt_sync`` ``LogStore`` and pushes that log to a fixed path in the
private ``kuhyx/syncs`` repo. This module is the PC-side reader used by the
per-minute trigger (see ``_trigger.py``).

This module is the only reader of both the remote record and the local cache;
the shutdown wrapper that used to read the cache went with the PC's waking
role.

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
    PUBLISHED_ALARM_MAX_AGE_SECONDS,
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


def _read_cache() -> tuple[int, int, float, float | None] | None:
    """Read the cached alarm.

    Returns:
        ``(hour, minute, fetched_at, published_at)``, or None if there is no
        usable cache. ``published_at`` is None for a cache written before it
        was recorded, or by the GitHub mirror.
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
    published_at = cached.get("published_at")
    if not isinstance(published_at, float | int):
        published_at = None
    if not isinstance(hour, int) or not isinstance(minute, int):
        return None
    if not isinstance(fetched_at, (int, float)):
        return None
    if not in_range(hour, minute):
        return None
    return hour, minute, float(fetched_at), published_at


def _write_cache(hour: int, minute: int, published_at: float | None) -> None:
    """Persist a freshly fetched alarm so later reads survive a network loss.

    Failures are logged and swallowed: an unwritable cache degrades the next
    read to a live fetch, which is not worth failing a trigger tick over.

    Args:
        hour: Hour of day, 0-23.
        minute: Minute of hour, 0-59.
        published_at: When the phone stamped the record, epoch seconds, or
            None when unknown. Cached alongside so a stale record cannot be
            laundered into freshness by a recent *fetch*.
    """
    entry = {
        "hour": hour,
        "minute": minute,
        "fetched_at": time.time(),
        "published_at": published_at,
    }
    try:
        ALARM_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with ALARM_CACHE_FILE.open("w") as handle:
            json.dump(entry, handle, indent=2)
    except OSError as exc:
        _logger.warning("Cannot write alarm cache: %s", exc)


def _has_lapsed(published_at: float | None) -> bool:
    """Whether a record is too old for the phone to still mean it.

    An unknown stamp is never treated as lapsed: refusing an alarm we merely
    failed to date would be a worse failure than honouring it.

    Args:
        published_at: When the phone stamped the record, or None if unknown.

    Returns:
        True when the record is past ``PUBLISHED_ALARM_MAX_AGE_SECONDS``.
    """
    if published_at is None:
        return False
    return time.time() - published_at > PUBLISHED_ALARM_MAX_AGE_SECONDS


def get_alarm(*, max_cache_age_seconds: float = ALARM_CACHE_MAX_AGE_SECONDS) -> Alarm:
    """Resolve the alarm to fire today, degrading gracefully at every step.

    Resolution order:

    1. A cache entry younger than *max_cache_age_seconds* (no network).
    2. A live fetch, Firebase first (cached on success).
    3. Any cache entry, however stale — better an old alarm than none.
    4. ``FALLBACK_ALARM_HOUR:00``.

    A record the phone published longer ago than
    ``PUBLISHED_ALARM_MAX_AGE_SECONDS`` is skipped at *every* step, including
    the cache — the check is on when the phone said it, not on when we last
    fetched, because a value re-fetched seconds ago can still be a time the
    phone moved on from months back.

    Args:
        max_cache_age_seconds: How long a cached read is served without
            re-fetching. Injectable so tests and ``--show`` can force a live
            read.

    Returns:
        The resolved alarm. Always succeeds.
    """
    cached = _read_cache()
    if cached is not None and _has_lapsed(cached[3]):
        _logger.info("Cached alarm lapsed — the phone has not published since")
        cached = None
    if cached is not None:
        hour, minute, fetched_at, _ = cached
        if time.time() - fetched_at < max_cache_age_seconds:
            return Alarm(hour, minute, "cache")

    remote = fetch_remote_alarm()
    if remote is not None and _has_lapsed(remote[2]):
        _logger.info("Published alarm lapsed — the phone has not published since")
        remote = None
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
