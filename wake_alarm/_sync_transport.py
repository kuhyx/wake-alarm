"""Fetching the alarm the phone pushed — Firebase first, GitHub as mirror.

Split out of ``_sync.py`` for the 250-line cap, along the seam item 8 needs:
this module is the **transport** (token discovery and the two backends), while
``_sync.py`` keeps **resolution** (cache, staleness, fallback) and the CLI.
Item 8 adds a dismissal-record reader, which belongs here beside the alarm
reader rather than inside the resolution chain.

``ALARM_CACHE_FILE`` deliberately does NOT live here: the suite patches
``wake_alarm._sync.ALARM_CACHE_FILE`` to keep tests off
``~/.config/wake_alarm/alarm_cache.json``, which ``shutdown-wrapper.sh`` reads
at poweroff, and moving that binding would silently reconnect the tests to the
real file.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from wake_alarm._alarm_payload import newest_alarm, parse_log
from wake_alarm._constants import (
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


def _read_token_config() -> str | None:
    """Read the token from this package's own JSON config.

    Returns:
        The token, or None if the file is missing, unreadable, malformed, or
        holds no usable token.
    """
    try:
        with SYNC_CONFIG_FILE.open() as handle:
            config = json.load(handle)
    except OSError, json.JSONDecodeError:
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


def fetch_firebase_logs() -> list[tuple[str, str]] | None:
    """Fetch every device's raw ``alarm.json`` from Firebase.

    Discovers device directories rather than reading one fixed path: the
    phone's device id is migrating from the constant "phone" to a per-install
    uuid, and a reader pinned to the old path would stop seeing the alarm the
    moment the phone migrated — falling back to FALLBACK_ALARM_HOUR, i.e.
    waking the user at the wrong time. Listing covers both ids, and
    SYNC_ALARM_PATH remains as a last resort for a backend that cannot list.

    Shared by the alarm reader and ``_weight``: the morning session's
    weigh-in rides on the same record, so one fetch serves both.

    Returns None — never raises — for every failure mode, including
    ``crdt_sync`` not being importable on this interpreter, so the caller can
    fall back to GitHub and then to the cache.

    Returns:
        ``(device_id, raw_json)`` per device, or None if unconfigured or
        unreadable.
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
    return published


def _fetch_firebase_alarm() -> tuple[int, int, float | None] | None:
    """The newest alarm any device has pushed to Firebase, or None."""
    published = fetch_firebase_logs()
    return None if published is None else newest_alarm(published)


def _fetch_github_alarm() -> tuple[int, int, float | None] | None:
    """Fetch the alarm the phone last pushed to GitHub.

    Uses the raw media type so the Contents API returns the file body directly
    rather than base64-wrapped JSON.

    Returns:
        ``(hour, minute, published_at)`` -- age unknown on this path -- or
        None if unconfigured, unreachable, or
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

    parsed = parse_log(raw)
    if parsed is None:
        return None
    # The mirror is a single fixed path with no per-field HLC to read, so its
    # age is unknown rather than fresh. See hlc_instant on why that is treated
    # as trustworthy.
    return (*parsed, None)


def fetch_remote_alarm() -> tuple[int, int, float | None] | None:
    """Fetch the alarm the phone last pushed, Firebase first.

    GitHub is tried only when Firebase yields nothing, which covers both the
    not-yet-migrated machine and a Firebase outage. Once every device has
    moved, deleting the GitHub branch is the whole retirement.

    Returns:
        ``(hour, minute, published_at)``, or None if no backend has a
        usable answer. ``published_at`` is epoch seconds, or None when the
        record carries no readable stamp.
    """
    return _fetch_firebase_alarm() or _fetch_github_alarm()
