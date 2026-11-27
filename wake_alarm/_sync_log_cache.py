"""The last successfully-fetched Firebase logs, read back when offline.

``fetch_firebase_logs`` writes the cache after every success and, for the
display readers that ask for it (``_weight``, ``_energy`` via
``_field_reader``), serves it when a fetch fails, so they still answer with
the newest known data while the network is down. The alarm path and the
enforcement checks do not ask: they must see a failed read as a failure.
The alarm time keeps its own ``ALARM_CACHE_FILE``; this is the *details*
half of offline-first: the raw per-device logs, not just the hour and
minute.
"""

from __future__ import annotations

import json
import logging

from wake_alarm._constants import SYNC_LOGS_CACHE_FILE

_logger = logging.getLogger(__name__)

#: The arity of one cached ``(device_id, raw_log_json)`` pair.
_PAIR_ARITY = 2


def write_synced_logs_cache(published: list[tuple[str, str]]) -> None:
    """Persist [published] ``(device_id, raw_log_json)`` pairs.

    A failed write is logged and swallowed: the fetch already succeeded, and
    losing the cache must not crash the per-minute trigger or a reader.
    """
    entry = {"logs": [[device_id, raw] for device_id, raw in published]}
    try:
        SYNC_LOGS_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        SYNC_LOGS_CACHE_FILE.write_text(json.dumps(entry, indent=2))
    except OSError as exc:
        _logger.warning("Cannot write synced-logs cache: %s", exc)


def read_synced_logs_cache() -> list[tuple[str, str]] | None:
    """The cached pairs, or None when absent, unreadable or malformed.

    A corrupt cache degrades to "nothing cached" — the fetch then degrades
    further to its own fallbacks — never to a crash.
    """
    try:
        cached = json.loads(SYNC_LOGS_CACHE_FILE.read_text())
    except OSError, json.JSONDecodeError:
        return None
    if not isinstance(cached, dict):
        return None
    logs = cached.get("logs")
    if not isinstance(logs, list) or not logs:
        return None
    pairs = [
        (pair[0], pair[1])
        for pair in logs
        if (
            isinstance(pair, list)
            and len(pair) == _PAIR_ARITY
            and isinstance(pair[0], str)
            and isinstance(pair[1], str)
        )
    ]
    return pairs or None
