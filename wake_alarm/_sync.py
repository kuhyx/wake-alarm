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
import urllib.error
import urllib.request

from wake_alarm._alarm_payload import in_range, newest_alarm, parse_log
from wake_alarm._constants import (
    ALARM_CACHE_FILE,
    ALARM_CACHE_MAX_AGE_SECONDS,
    FALLBACK_ALARM_HOUR,
    SYNC_ALARM_FILENAME,
    SYNC_ALARM_PATH,
    SYNC_API_BASE,
    SYNC_APP_NAME,
    SYNC_CONFIG_FILE,
    SYNC_DEVICES_PREFIX,
    SYNC_HTTP_TIMEOUT_SECONDS,
    SYNC_REPO_NAME,
    SYNC_REPO_OWNER,
    SYNC_TOKEN_FALLBACK_FILES,
)
from wake_alarm._logging_setup import configure_logging

_logger = logging.getLogger(__name__)

# Optional at runtime, exactly like python-kasa in _smart_plug.py: the trigger
# runs every minute under /usr/bin/python, so a dependency that failed to
# install must degrade this read to the GitHub path, not raise.
try:
    from crdt_sync import ConfigError, firebase_client_for
    from crdt_sync._config import CONFIG_FILE as FIREBASE_CONFIG_FILE
    from crdt_sync._firebase_auth import FirebaseAuthError
    from crdt_sync._remote import RemoteSyncError

    _FIREBASE_AVAILABLE = True
except ImportError:
    _FIREBASE_AVAILABLE = False
    _logger.info("crdt_sync is not installed; reading the alarm from GitHub")


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


def _fetch_firebase_alarm() -> tuple[int, int] | None:
    """Fetch the newest alarm any device has pushed to Firebase.

    Discovers device directories rather than reading one fixed path: the
    phone's device id is migrating from the constant "phone" to a per-install
    uuid, and a reader pinned to the old path would stop seeing the alarm the
    moment the phone migrated — falling back to FALLBACK_ALARM_HOUR, i.e.
    waking the user at the wrong time. Listing covers both ids, and
    SYNC_ALARM_PATH remains as a last resort for a backend that cannot list.

    Returns None — never raises — for every failure mode, including
    ``crdt_sync`` not being importable on this interpreter, so the caller can
    fall back to GitHub and then to the cache.

    Returns:
        The (hour, minute) pair, or None if unconfigured or unreadable.
    """
    if not _FIREBASE_AVAILABLE:
        return None

    # Checked before constructing anything, so an unconfigured machine never
    # touches the network (and a socket-blocking test suite stays quiet).
    if not FIREBASE_CONFIG_FILE.is_file():
        _logger.info("Firebase not configured at %s", FIREBASE_CONFIG_FILE)
        return None

    try:
        client = firebase_client_for(SYNC_APP_NAME)
        published: list[tuple[str, str]] = []
        for device_id in client.list_directory(SYNC_DEVICES_PREFIX):
            raw = client.get_file_text(
                f"{SYNC_DEVICES_PREFIX}/{device_id}/{SYNC_ALARM_FILENAME}"
            )
            if raw is not None:
                published.append((device_id, raw))
        if not published:
            # No directories listed (or none held a file): still try the
            # legacy fixed path, so a phone that has not migrated is read.
            raw = client.get_file_text(SYNC_ALARM_PATH)
            if raw is None:
                _logger.info("No alarm published to Firebase yet")
                return None
            published.append(("phone", raw))
    except (ConfigError, FirebaseAuthError, RemoteSyncError, OSError) as exc:
        _logger.info("Cannot fetch the alarm from Firebase: %s", exc)
        return None

    return newest_alarm(published)


def _fetch_github_alarm() -> tuple[int, int] | None:
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

    return parse_log(raw)


def fetch_remote_alarm() -> tuple[int, int] | None:
    """Fetch the alarm the phone last pushed, Firebase first.

    GitHub is tried only when Firebase yields nothing, which covers both the
    not-yet-migrated machine and a Firebase outage. Once every device has
    moved, deleting the GitHub branch is the whole retirement.

    Returns:
        The (hour, minute) pair, or None if no backend has a usable answer.
    """
    return _fetch_firebase_alarm() or _fetch_github_alarm()


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
