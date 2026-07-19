"""Read the alarm time the phone pushed, with an on-disk cache and fallbacks.

The phone app (``phone_app/``) is the sole writer: it stores the chosen alarm
in a ``crdt_sync`` ``LogStore`` and pushes that log to a fixed path in the
private ``kuhyx/syncs`` repo. This module is the PC-side reader used by the
per-minute trigger (see ``_trigger.py``).

``shutdown-wrapper.sh`` reads the **same file** with ``jq`` for the hibernate
fallback path. The parse here mirrors it exactly (``.alarm.fields.alarm_hour``
and ``.alarm.fields.alarm_minute``, first tuple element) so the two readers
cannot drift.

Deliberately stdlib-only (``urllib.request`` + ``json``): the alarm runs under
``/usr/bin/python``, not a venv, so every added dependency is a production
install-path hazard (see ``CLAUDE.md``). A read is not worth that risk.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import logging
import sys
import time
from typing import Any
import urllib.error
import urllib.request

from wake_alarm._constants import (
    ALARM_CACHE_FILE,
    ALARM_CACHE_MAX_AGE_SECONDS,
    FALLBACK_ALARM_HOUR,
    MAX_HOUR,
    MAX_MINUTE,
    MIN_HOUR,
    MIN_MINUTE,
    SYNC_ALARM_PATH,
    SYNC_API_BASE,
    SYNC_CONFIG_FILE,
    SYNC_HTTP_TIMEOUT_SECONDS,
    SYNC_REPO_NAME,
    SYNC_REPO_OWNER,
    SYNC_TOKEN_FALLBACK_FILES,
)
from wake_alarm._logging_setup import configure_logging

_logger = logging.getLogger(__name__)

# Keys inside the crdt_sync log the phone writes.
_RECORD_ID = "alarm"
_HOUR_FIELD = "alarm_hour"
_MINUTE_FIELD = "alarm_minute"


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


def _in_range(hour: int, minute: int) -> bool:
    """Check that an (hour, minute) pair is a real wall-clock time.

    Guards both readers: a malformed sync payload and a corrupted cache must
    never become a fire time.

    Args:
        hour: Candidate hour.
        minute: Candidate minute.

    Returns:
        True if both values are within a 24-hour clock.
    """
    return MIN_HOUR <= hour <= MAX_HOUR and MIN_MINUTE <= minute <= MAX_MINUTE


def _read_token_config() -> str | None:
    """Read the token from this package's own JSON config.

    Returns:
        The token, or None if the file is missing, unreadable, malformed, or
        holds no usable token.
    """
    try:
        with SYNC_CONFIG_FILE.open() as handle:
            config = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(config, dict):
        return None
    token = config.get("token")
    if not isinstance(token, str) or not token:
        return None
    return token


def _read_token_fallback() -> str | None:
    """Read the token from a sibling app's raw single-line token file.

    Returns:
        The first usable token found, or None if none of the fallback files
        exists or holds one.
    """
    for path in SYNC_TOKEN_FALLBACK_FILES:
        try:
            token = path.read_text().strip()
        except OSError:
            continue
        if token:
            _logger.debug("Using sync token from %s", path)
            return token
    return None


def _read_token() -> str | None:
    """Read the GitHub token, preferring this package's own config.

    Falls back to the sibling companion apps' token files so one repo-scoped
    PAT covers every app syncing through ``kuhyx/syncs``.

    Returns:
        The token, or None if no configured source holds one.
    """
    # No warning on a miss here: the caller reports "no token" once. Logging
    # twice for one unconfigured file makes every tick noisy in the journal.
    return _read_token_config() or _read_token_fallback()


def _extract_field(log: dict[str, Any], field: str) -> int | None:
    """Pull one integer field out of the phone's crdt_sync log.

    The stored shape is ``{"alarm": {"fields": {"<field>": [value, "<hlc>"]}}}``
    — each field is a (value, HLC) pair, so the value is element 0.

    Args:
        log: The parsed log JSON.
        field: Field name to extract (e.g. ``alarm_hour``).

    Returns:
        The integer value, or None if anything about the shape is unexpected.
    """
    record = log.get(_RECORD_ID)
    if not isinstance(record, dict):
        return None
    fields = record.get("fields")
    if not isinstance(fields, dict):
        return None
    pair = fields.get(field)
    # bool is an int subclass; an alarm hour of True would be nonsense.
    if not isinstance(pair, list) or not pair:
        return None
    value = pair[0]
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _parse_log(raw: str) -> tuple[int, int] | None:
    """Parse the phone's log into an (hour, minute) pair.

    Args:
        raw: The raw JSON text returned by the Contents API.

    Returns:
        The (hour, minute) pair, or None if the payload is malformed or the
        values are out of range.
    """
    try:
        log = json.loads(raw)
    except json.JSONDecodeError:
        _logger.warning("Synced alarm is not valid JSON")
        return None
    if not isinstance(log, dict):
        return None
    hour = _extract_field(log, _HOUR_FIELD)
    minute = _extract_field(log, _MINUTE_FIELD)
    if hour is None or minute is None:
        _logger.warning("Synced alarm is missing hour/minute fields")
        return None
    if not _in_range(hour, minute):
        _logger.warning("Synced alarm out of range: %d:%d", hour, minute)
        return None
    return hour, minute


def fetch_remote_alarm() -> tuple[int, int] | None:
    """Fetch the alarm the phone last pushed to GitHub.

    Uses the raw media type so the Contents API returns the file body directly
    rather than base64-wrapped JSON.

    Returns:
        The (hour, minute) pair, or None if unconfigured, unreachable, or
        malformed. Never raises — a failed read must degrade to the cache,
        not crash the trigger.
    """
    token = _read_token()
    if token is None:
        # INFO, not WARNING: get_alarm() runs on every one-minute trigger tick,
        # so a persistent condition logged loudly here is 1440 identical
        # journal lines a day. The trigger warns once, at the moment it
        # actually fires on a degraded source — that is the actionable event.
        _logger.info("No sync token configured at %s", SYNC_CONFIG_FILE)
        return None

    url = (
        f"{SYNC_API_BASE}/repos/{SYNC_REPO_OWNER}/{SYNC_REPO_NAME}"
        f"/contents/{SYNC_ALARM_PATH}"
    )
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.raw",
        },
    )
    # The URL is built from module constants, never from remote input, but
    # assert the scheme anyway: this call carries a credential, and an http://
    # or file:// target would leak it. Belt and braces for a bad edit above.
    if request.type != "https":
        _logger.error("Refusing to send the sync token over %s", request.type)
        return None
    try:
        with urllib.request.urlopen(
            request, timeout=SYNC_HTTP_TIMEOUT_SECONDS
        ) as response:
            raw = response.read().decode("utf-8")
    except (urllib.error.URLError, OSError, UnicodeDecodeError) as exc:
        # INFO for the same reason as the no-token path: a persistent failure
        # (404 because the phone never pushed, an expired token, no network)
        # would otherwise be one WARNING per cache expiry, forever.
        _logger.info("Cannot fetch synced alarm: %s", exc)
        return None

    return _parse_log(raw)


def _read_cache() -> tuple[int, int, float] | None:
    """Read the cached alarm.

    Returns:
        An (hour, minute, fetched_at) triple, or None if there is no usable
        cache.
    """
    try:
        with ALARM_CACHE_FILE.open() as handle:
            cached = json.load(handle)
    except (OSError, json.JSONDecodeError):
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
    if not _in_range(hour, minute):
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
