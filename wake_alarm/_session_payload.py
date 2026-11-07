"""Parse the phone's morning session out of the ``crdt_sync`` log.

Pure, like ``_alarm_payload``: JSON in, one ``SessionRecord`` out, no clock,
no disk. The phone (``session_sync.dart``) publishes two fields on the same
``alarm.json`` record the alarm time rides on:

* ``morning_sessions`` -- the newest finished sessions, each the phone's own
  session JSON with ``outcome`` ``completed`` or ``failed``;
* ``current_session`` -- the live session while one is running (``outcome``
  ``active``), ``{}`` once it has finished.

Selection is by content, never by comparing the two fields' HLC stamps: for
one date a finished record beats the in-progress one whatever the stamps say,
so a phone that lost the network at finish and never cleared
``current_session`` still resolves to the finished morning.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from typing import Any

from wake_alarm._alarm_payload import extract_hlc, hlc_instant
from wake_alarm._constants import SESSION_CURRENT_FIELD, SESSIONS_FIELD

_logger = logging.getLogger(__name__)

# The phone's outcome names, mapped to the PC's. ``active`` is the phone's
# word for a live session; the PC file says ``in_progress`` so a reader never
# has to know the Dart enum.
_OUTCOMES: dict[str, str] = {
    "active": "in_progress",
    "completed": "completed",
    "failed": "failed",
}
_FINISHED_PHASE = 1
_LIVE_PHASE = 0


@dataclass(frozen=True)
class SessionRecord:
    """One morning as the phone described it."""

    date: str
    outcome: str
    started_at: str
    finished_at: str | None
    energy: int | None
    weight_kg: float | None
    re_rings: int
    device_id: str
    published_at: float | None
    # Names (``_session_legs.LEGS``) of the legs the phone has passed.
    passed_legs: tuple[str, ...] = ()

    @property
    def finished(self) -> bool:
        """Whether the phone considers this morning over."""
        return self.outcome != "in_progress"


def _int_or_none(value: object) -> int | None:
    """An int, refusing bools (an int subclass) and anything else."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _float_or_none(value: object) -> float | None:
    """A float from an int or float, refusing bools."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _passed_legs(value: object) -> tuple[str, ...]:
    """Leg names in the phone's ``passed`` map that carry a pass timestamp."""
    if not isinstance(value, dict):
        return ()
    return tuple(
        name
        for name, entry in value.items()
        if isinstance(name, str)
        and isinstance(entry, dict)
        and isinstance(entry.get("at"), str)
    )


def record_from_json(
    value: object,
    *,
    device_id: str,
    published_at: float | None,
) -> SessionRecord | None:
    """Build a record from one phone session JSON, or None if malformed."""
    if not isinstance(value, dict):
        return None
    date, started, outcome = (
        value.get("date"),
        value.get("started_at"),
        value.get("outcome"),
    )
    if not isinstance(date, str) or not isinstance(started, str):
        return None
    if not isinstance(outcome, str) or outcome not in _OUTCOMES:
        return None
    mapped = _OUTCOMES[outcome]
    updated = value.get("updated_at")
    finished_at = (
        updated if mapped != "in_progress" and isinstance(updated, str) else None
    )
    return SessionRecord(
        date=date,
        outcome=mapped,
        started_at=started,
        finished_at=finished_at,
        energy=_int_or_none(value.get("energy")),
        weight_kg=_float_or_none(value.get("weight_kg")),
        re_rings=_int_or_none(value.get("re_rings")) or 0,
        device_id=device_id,
        published_at=published_at,
        passed_legs=_passed_legs(value.get("passed")),
    )


def _field_value(log: dict[str, Any], field: str) -> object:
    """The value half of one ``(value, HLC)`` pair, or None."""
    record = log.get("alarm")
    fields = record.get("fields") if isinstance(record, dict) else None
    pair = fields.get(field) if isinstance(fields, dict) else None
    return pair[0] if isinstance(pair, list) and pair else None


def _rank_key(record: SessionRecord, hlc: str) -> tuple[str, int, str, str]:
    """Newest date first; a finished morning beats a live one on the same date."""
    phase = _FINISHED_PHASE if record.finished else _LIVE_PHASE
    return (record.date, phase, hlc, record.device_id)


def sessions_on_log(
    log: dict[str, Any], device_id: str
) -> list[tuple[tuple[str, int, str, str], SessionRecord]]:
    """Every usable session one device published, with its ranking key."""
    ranked: list[tuple[tuple[str, int, str, str], SessionRecord]] = []
    history = _field_value(log, SESSIONS_FIELD)
    history_hlc = extract_hlc(log, SESSIONS_FIELD)
    history_at = hlc_instant(history_hlc)
    for entry in history if isinstance(history, list) else []:
        record = record_from_json(entry, device_id=device_id, published_at=history_at)
        if record is not None and record.finished:
            ranked.append((_rank_key(record, history_hlc), record))
    live_hlc = extract_hlc(log, SESSION_CURRENT_FIELD)
    live = record_from_json(
        _field_value(log, SESSION_CURRENT_FIELD),
        device_id=device_id,
        published_at=hlc_instant(live_hlc),
    )
    if live is not None and not live.finished:
        ranked.append((_rank_key(live, live_hlc), live))
    return ranked


def newest_session(published: list[tuple[str, str]]) -> SessionRecord | None:
    """The newest morning across every device's log, or None.

    Args:
        published: ``(device_id, raw_json)`` per device, in any order.

    Returns:
        The record with the newest date -- finished before live on that date,
        then by HLC, then by ``device_id`` so two installs never alternate.
    """
    ranked: list[tuple[tuple[str, int, str, str], SessionRecord]] = []
    for device_id, raw in published:
        try:
            log = json.loads(raw)
        except json.JSONDecodeError:
            _logger.info("Ignoring unparsable session log from %r", device_id)
            continue
        if not isinstance(log, dict):
            continue
        ranked.extend(sessions_on_log(log, device_id))
    if not ranked:
        return None
    return max(ranked, key=lambda entry: entry[0])[1]
