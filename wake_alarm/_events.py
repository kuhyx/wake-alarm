"""Named PC events for ``events.jsonl`` -- the audit's half of the timeline.

Every event in ``DOCS-wake-enforcement.md`` goes through :func:`emit`, which
logs one INFO record carrying a top-level ``event`` key and a ``fields``
object; the JSONL sink (``_log_sink``) turns both into keys of the line, so
the audit can select on ``.event`` with no message parsing.

Jobs that run every minute (``fallback_tick``) or every 15 minutes
(``rtc_armed``) must log a decision once, not on every run. The shared
``DedupeFilter`` remembers a single fingerprint for everything, so two such
streams interleaving would defeat it; :func:`emit_on_change` instead keeps
the last value per event name in ``EVENT_STATE_FILE``.
"""

from __future__ import annotations

import json
import logging

from wake_alarm._constants import EVENT_STATE_FILE

_logger = logging.getLogger("wake_alarm.events")


def emit(event: str, message: str, **fields: object) -> None:
    """Log ``event`` with ``fields`` as one structured INFO record."""
    _logger.info(
        "%s: %s", event, message, extra={"event": event, "fields": dict(fields)}
    )


def _read_state() -> dict[str, str]:
    """The persisted last-logged values; empty when absent or unreadable."""
    try:
        raw = json.loads(EVENT_STATE_FILE.read_text(encoding="utf-8"))
    except OSError, ValueError:
        return {}
    if not isinstance(raw, dict):
        return {}
    return {k: v for k, v in raw.items() if isinstance(v, str)}


def _write_state(state: dict[str, str]) -> None:
    """Persist ``state`` atomically; a failure only costs a repeated line."""
    tmp = EVENT_STATE_FILE.with_name(EVENT_STATE_FILE.name + ".tmp")
    try:
        EVENT_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(state, sort_keys=True), encoding="utf-8")
        tmp.replace(EVENT_STATE_FILE)
    except OSError as exc:
        _logger.info("Cannot persist %s: %s", EVENT_STATE_FILE, exc)


def last_value(slot: str) -> str | None:
    """What was last remembered under ``slot``, or None."""
    return _read_state().get(slot)


def remember(slot: str, value: str | None) -> None:
    """Store ``value`` under ``slot`` (None forgets it)."""
    state = _read_state()
    if value is None:
        if slot not in state:
            return
        del state[slot]
    elif state.get(slot) == value:
        return
    else:
        state[slot] = value
    _write_state(state)


def emit_on_change(event: str, key: str, message: str, **fields: object) -> bool:
    """Emit ``event`` only when ``key`` differs from the last one logged.

    Returns:
        True when the event was logged.
    """
    if last_value(event) == key:
        return False
    emit(event, message, **fields)
    remember(event, key)
    return True
