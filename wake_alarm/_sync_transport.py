"""Fetching the alarm the phone pushed — Firebase first, GitHub as mirror.

Split out of ``_sync.py`` for the 250-line cap, along the seam item 8 needs:
this module is the **transport** (token discovery and the two backends), while
``_sync.py`` keeps **resolution** (cache, staleness, fallback) and the CLI.

Both backends hold the same end-to-end encrypted layout
(``wake-alarm-sync/devices-e2e``), sealed under the shared crdt-sync
passphrase (``~/.config/crdt-sync/password``). Every read goes through
``crdt_sync.open_encrypted_client``, which also copies the old plaintext
prefix over once per process, so a phone not yet updated is still seen. A
missing or wrong passphrase reads as "nothing published" (fail closed: the
resolution chain falls to the cache, then 08:00), never as plaintext.

``ALARM_CACHE_FILE`` deliberately does NOT live here: the suite patches
``wake_alarm._sync.ALARM_CACHE_FILE`` to keep tests off
``~/.config/wake_alarm/alarm_cache.json``, which ``shutdown-wrapper.sh`` reads
at poweroff, and moving that binding would silently reconnect the tests to the
real file.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from wake_alarm._alarm_payload import newest_alarm
from wake_alarm._constants import (
    SYNC_ALARM_FILENAME,
    SYNC_ALARM_PATH,
    SYNC_APP_NAME,
    SYNC_CONFIG_FILE,
    SYNC_HTTP_TIMEOUT_SECONDS,
    SYNC_LEGACY_PREFIX,
    SYNC_REPO_NAME,
    SYNC_REPO_OWNER,
    SYNC_TOKEN_FALLBACK_FILES,
)

if TYPE_CHECKING:
    from crdt_sync import Argon2Params, RemoteStore

_logger = logging.getLogger(__name__)

# Optional at runtime, exactly like python-kasa in _smart_plug.py: the trigger
# runs every minute under /usr/bin/python, so a dependency that failed to
# install must degrade this read to the cache, not raise. Without crdt_sync
# (and its pynacl/argon2-cffi) nothing can be decrypted, so neither backend
# is read.
try:
    from crdt_sync import (
        PASSWORD_FILE,
        ConfigError,
        E2eDecryptError,
        E2eLayout,
        E2eLockedError,
        GitHubSyncClient,
        firebase_client_for,
        open_encrypted_client,
    )
    from crdt_sync._config import CONFIG_FILE as FIREBASE_CONFIG_FILE
    from crdt_sync._firebase_auth import FirebaseAuthError
    from crdt_sync._remote import RemoteSyncError

    _FIREBASE_AVAILABLE = True
except ImportError:
    _FIREBASE_AVAILABLE = False
    _logger.info("crdt_sync is not installed; the alarm cannot be fetched")

#: Argon2id cost for a header this machine creates; None is the library's
#: default. Only tests lower it.
E2E_ARGON2_PARAMS: Argon2Params | None = None


def _read_passphrase() -> str:
    """The shared crdt-sync passphrase, or "" (locked) when there is none."""
    try:
        return PASSWORD_FILE.read_text().strip()
    except OSError:
        return ""


def _read_sealed(store: RemoteStore, path: str) -> str | None:
    """One device's decrypted record; None when absent or undecryptable."""
    try:
        return store.get_file_text(path)
    except E2eDecryptError as exc:
        _logger.info("Skipping an unreadable alarm at %s: %s", path, exc)
        return None


def _read_published(client: RemoteStore) -> list[tuple[str, str]]:
    """Every device's decrypted ``alarm.json`` through ``client``.

    Discovers device directories rather than reading one fixed path: the
    phone's device id is migrating from the constant "phone" to a per-install
    uuid, and a reader pinned to the old path would stop seeing the alarm the
    moment the phone migrated -- falling back to FALLBACK_ALARM_HOUR, i.e.
    waking the user at the wrong time. Listing covers both ids, and
    SYNC_ALARM_PATH remains as a last resort for a backend that cannot list.

    Raises:
        E2eLockedError: No usable key; the caller reads that as nothing.
    """
    store, layout = open_encrypted_client(
        client,
        SYNC_LEGACY_PREFIX,
        passphrase=_read_passphrase(),
        params=E2E_ARGON2_PARAMS,
    )
    published: list[tuple[str, str]] = []
    for device_id in store.list_directory(layout.prefix):
        raw = _read_sealed(store, f"{layout.prefix}/{device_id}/{SYNC_ALARM_FILENAME}")
        if raw is not None:
            published.append((device_id, raw))
    if not published:
        # No directories listed (or none held a file): still try the
        # legacy fixed path, so a phone that has not migrated is read.
        raw = _read_sealed(store, SYNC_ALARM_PATH)
        if raw is not None:
            published.append(("phone", raw))
    return published


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

    Falls back to diet_guard's token file so one repo-scoped PAT covers
    every app syncing through ``kuhyx/syncs``.

    Returns:
        The token, or None if no configured source holds one.
    """
    # No warning on a miss here: the caller reports "no token" once. Logging
    # twice for one unconfigured file makes every tick noisy in the journal.
    return _read_token_config() or _read_token_fallback()


def fetch_firebase_logs() -> list[tuple[str, str]] | None:
    """Fetch every device's decrypted ``alarm.json`` from Firebase.

    Shared by the alarm reader and ``_weight``: the morning session's
    weigh-in rides on the same record, so one fetch serves both.

    Returns None — never raises — for every failure mode, including
    ``crdt_sync`` not being importable on this interpreter and a locked
    (no or wrong passphrase) store, so the caller can fall back to GitHub and
    then to the cache.

    Returns:
        ``(device_id, raw_json)`` per device, or None if unconfigured,
        locked or unreadable.
    """
    if not _FIREBASE_AVAILABLE:
        return None

    # Checked before constructing anything, so an unconfigured machine never
    # touches the network (and a socket-blocking test suite stays quiet).
    if not FIREBASE_CONFIG_FILE.is_file():
        _logger.info("Firebase not configured at %s", FIREBASE_CONFIG_FILE)
        return None

    try:
        published = _read_published(firebase_client_for(SYNC_APP_NAME))
    except (
        ConfigError,
        FirebaseAuthError,
        RemoteSyncError,
        OSError,
        E2eLockedError,
    ) as exc:
        _logger.info("Cannot fetch the alarm from Firebase: %s", exc)
        return None
    if not published:
        _logger.info("No alarm published to Firebase yet")
        return None
    return published


def _fetch_firebase_alarm() -> tuple[int, int, float | None] | None:
    """The newest alarm any device has pushed to Firebase, or None."""
    published = fetch_firebase_logs()
    return None if published is None else newest_alarm(published)


def _fetch_github_alarm() -> tuple[int, int, float | None] | None:
    """Fetch the alarm the phone last pushed to the GitHub mirror.

    The same encrypted layout as Firebase (the phone's mirror store writes
    both), read through ``crdt_sync``'s Contents API client.

    Returns:
        ``(hour, minute, published_at)``, or None if unconfigured,
        unreachable, locked or malformed. Never raises — a failed read must
        degrade to the cache, not crash the trigger.
    """
    if not _FIREBASE_AVAILABLE:
        return None
    token = _read_token()
    if token is None:
        # INFO, not WARNING: get_alarm() runs on every one-minute trigger tick,
        # so a persistent condition logged loudly here is 1440 identical
        # journal lines a day. The trigger warns once, at the moment it
        # actually fires on a degraded source — that is the actionable event.
        _logger.info("No sync token configured at %s", SYNC_CONFIG_FILE)
        return None
    client = GitHubSyncClient(
        SYNC_REPO_OWNER,
        SYNC_REPO_NAME,
        token,
        timeout_seconds=SYNC_HTTP_TIMEOUT_SECONDS,
    )
    try:
        # Read-only on the mirror: only the phone may create its header. A
        # PC-made one (fresh salt) would leave every blob the phone sealed
        # unreadable there, and could mislead a phone opening offline.
        if client.get_file_text(E2eLayout.of(SYNC_LEGACY_PREFIX).e2e_path) is None:
            _logger.info("No encrypted alarm on the GitHub mirror yet")
            return None
        published = _read_published(client)
    except (RemoteSyncError, OSError, E2eLockedError) as exc:
        # INFO for the same reason as the no-token path: a persistent failure
        # would otherwise be one WARNING per cache expiry, forever.
        _logger.info("Cannot fetch synced alarm: %s", exc)
        return None
    return newest_alarm(published) if published else None


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
