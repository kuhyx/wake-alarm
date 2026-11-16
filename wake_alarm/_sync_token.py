"""The GitHub-mirror token: this package's own config, then a sibling app's.

Split out of ``_sync_transport.py`` for the 250-line cap. Only the GitHub
fallback needs a token; Firebase authenticates through ``crdt_sync``'s own
cached refresh token. Stdlib-only on purpose: the per-minute trigger runs
``/usr/bin/python`` and must import this even when ``crdt_sync`` failed to
install.
"""

from __future__ import annotations

import json
import logging

from wake_alarm._constants import SYNC_CONFIG_FILE, SYNC_TOKEN_FALLBACK_FILES

_logger = logging.getLogger(__name__)


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


def read_token() -> str | None:
    """Read the GitHub token, preferring this package's own config.

    Falls back to diet_guard's token file so one repo-scoped PAT covers
    every app syncing through ``kuhyx/syncs``.

    Returns:
        The token, or None if no configured source holds one.
    """
    # No warning on a miss here: the caller reports "no token" once. Logging
    # twice for one unconfigured file makes every tick noisy in the journal.
    return _read_token_config() or _read_token_fallback()
