"""Merge the v2 enforcement fields across every device's ``alarm.json``.

Pure: ``(device_id, raw_json)`` pairs in -- the same list
``_sync_transport.fetch_firebase_logs`` returns and ``_session_payload``
reads -- one :class:`EnforcementView` out. Every field is a crdt_sync
``(value, HLC)`` pair:

* ``ring_started`` and ``stick_state`` describe *now*, so the newest HLC wins
  (``device_id`` breaks an exact tie, so two installs never alternate);
* ``escapes`` and ``phone_events`` are history, so they are the **union**:
  newest-wins on a list would let a reinstalled phone, publishing an empty
  history, erase every escape and event the old install recorded.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
import logging
from typing import TYPE_CHECKING, Any

from wake_alarm._alarm_payload import extract_hlc
from wake_alarm._constants import (
    ESCAPE_HATCH_LAST_DAY,
    ESCAPE_REASON_MIN_CHARS,
    ESCAPES_FIELD,
    PHONE_EVENTS_FIELD,
    RING_STARTED_FIELD,
    STICK_STATE_FIELD,
)
from wake_alarm._enforcement_records import (
    Escape,
    PhoneEvent,
    RingStarted,
    StickState,
    escape_from,
    phone_event_from,
    ring_started_from,
    stick_state_from,
)

if TYPE_CHECKING:
    from collections.abc import Callable

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EnforcementView:
    """What every device together says about the enforcement fields."""

    ring_started: RingStarted | None = None
    escapes: tuple[Escape, ...] = ()
    stick_state: StickState | None = None
    phone_events: tuple[PhoneEvent, ...] = ()

    def ring_started_on(self, day: str) -> bool:
        """Whether the phone's ring screen opened on ``day``."""
        return self.ring_started is not None and self.ring_started.date == day

    def honoured_escapes(self) -> tuple[Escape, ...]:
        """Escapes the PC acts on; see :func:`is_honoured`."""
        return tuple(e for e in self.escapes if is_honoured(e))

    def escape_for(self, day: str) -> Escape | None:
        """The first honoured escape excusing ``day``, or None."""
        return next((e for e in self.honoured_escapes() if e.date == day), None)

    def escaped_dates(self) -> frozenset[str]:
        """Every morning an honoured escape excuses."""
        return frozenset(e.date for e in self.honoured_escapes())


def is_honoured(escape: Escape) -> bool:
    """An escape counts only inside the hatch's life and with a real reason.

    The phone hides the button after ``ESCAPE_HATCH_LAST_DAY`` and refuses a
    short reason; the PC checks both again so a stale or hand-edited record
    cannot cancel a penalty the phone itself would not have excused.
    """
    try:
        day = date.fromisoformat(escape.date)
    except ValueError:
        return False
    return (
        day <= ESCAPE_HATCH_LAST_DAY
        and len(escape.reason.strip()) >= ESCAPE_REASON_MIN_CHARS
    )


def _pair_value(log: dict[str, Any], field: str) -> object:
    """The value half of one ``(value, HLC)`` pair, or None."""
    record = log.get("alarm")
    fields = record.get("fields") if isinstance(record, dict) else None
    pair = fields.get(field) if isinstance(fields, dict) else None
    return pair[0] if isinstance(pair, list) and pair else None


def _newest[T](
    logs: list[tuple[str, dict[str, Any]]],
    field: str,
    build: Callable[[object], T | None],
) -> T | None:
    """The parseable value with the newest ``(HLC, device_id)``, or None."""
    ranked: list[tuple[tuple[str, str], T]] = []
    for device_id, log in logs:
        built = build(_pair_value(log, field))
        if built is not None:
            ranked.append(((extract_hlc(log, field), device_id), built))
    return max(ranked, key=lambda entry: entry[0])[1] if ranked else None


def _union[T](
    logs: list[tuple[str, dict[str, Any]]],
    field: str,
    build: Callable[[object], T | None],
    identity: Callable[[T], str],
) -> tuple[T, ...]:
    """Every parseable list entry across devices, first occurrence wins."""
    seen: set[str] = set()
    merged: list[T] = []
    for _, log in sorted(
        logs, key=lambda entry: extract_hlc(entry[1], field), reverse=True
    ):
        value = _pair_value(log, field)
        for raw in value if isinstance(value, list) else []:
            built = build(raw)
            if built is None or identity(built) in seen:
                continue
            seen.add(identity(built))
            merged.append(built)
    return tuple(merged)


def _event_identity(event: PhoneEvent) -> str:
    """Two devices reporting the same event at the same instant are one."""
    return json.dumps([event.at, event.kind, event.data], sort_keys=True, default=str)


def parse_logs(published: list[tuple[str, str]]) -> list[tuple[str, dict[str, Any]]]:
    """``(device_id, parsed_log)`` for every log that is a JSON object."""
    logs: list[tuple[str, dict[str, Any]]] = []
    for device_id, raw in published:
        try:
            log = json.loads(raw)
        except json.JSONDecodeError:
            _logger.info("Ignoring unparsable enforcement log from %r", device_id)
            continue
        if isinstance(log, dict):
            logs.append((device_id, log))
    return logs


def enforcement_view(published: list[tuple[str, str]]) -> EnforcementView:
    """Merge every device's v2 fields into one view."""
    logs = parse_logs(published)
    return EnforcementView(
        ring_started=_newest(logs, RING_STARTED_FIELD, ring_started_from),
        escapes=_union(logs, ESCAPES_FIELD, escape_from, lambda e: e.id),
        stick_state=_newest(logs, STICK_STATE_FIELD, stick_state_from),
        phone_events=_union(
            logs, PHONE_EVENTS_FIELD, phone_event_from, _event_identity
        ),
    )
