"""The carrot's rule: what a morning earns, as one signed ``exempt_until``.

Pure -- a ``SessionRecord`` (or none) in, the unsigned file body out. Split
from ``_session`` (fetch, sign, write, CLI) at the 250-line cap; this is the
half a reader wants when asking "why is the PC open right now".

* nothing started today: exempt until the alarm plus ``SESSION_NONE_GRACE``
  -- being up before the alarm is the goal, and the phone rings at the alarm
  regardless, so a dismiss that has not produced a session by then means
  "not up";
* live: ``min(started_at + 90 min, 09:30)``, relative so an aborted early
  alarm cannot bank hours;
* completed inside that cutoff: 11:00; completed later, or failed: nothing.
"""

from __future__ import annotations

from datetime import datetime, time
import logging
from typing import TYPE_CHECKING

from wake_alarm._constants import (
    SESSION_COMPLETED_UNTIL,
    SESSION_NONE_GRACE,
    SESSION_PROVISIONAL_CAP,
    SESSION_PROVISIONAL_GRACE,
)

if TYPE_CHECKING:
    from wake_alarm._session_payload import SessionRecord

_logger = logging.getLogger(__name__)

NONE_OUTCOME = "none"


def _local(iso: str) -> datetime:
    """A phone-stamped naive local ISO instant as an aware local datetime."""
    return datetime.fromisoformat(iso).astimezone()


def _at(date: str, clock: tuple[int, int]) -> datetime:
    """Local wall-clock instant ``clock`` on the phone's session date."""
    return datetime.combine(
        datetime.fromisoformat(date).date(), time(*clock)
    ).astimezone()


def _cutoff(record: SessionRecord) -> datetime | None:
    """The instant a live morning stops being exempt: start + grace, capped."""
    try:
        started = _local(record.started_at)
    except ValueError:
        _logger.info(
            "Session started_at %r unreadable; no exemption", record.started_at
        )
        return None
    return min(
        started + SESSION_PROVISIONAL_GRACE, _at(record.date, SESSION_PROVISIONAL_CAP)
    )


def exempt_until(record: SessionRecord) -> datetime | None:
    """When the carrot this morning earned runs out; None when it earned none.

    Live: the start plus one honest morning, capped -- relative so an early
    alarm cannot bank hours by aborting. Completed: the flat end, but only if
    it finished inside that same cutoff -- a phone switched back on at noon
    completes the legs then, and that must not un-lock anything. Failed: none.
    """
    cutoff = _cutoff(record)
    if cutoff is None or record.outcome == "failed":
        return None
    if record.outcome == "in_progress":
        return cutoff
    try:
        finished = _local(record.finished_at or "")
    except ValueError:
        _logger.info(
            "Session finished_at %r unreadable; no exemption", record.finished_at
        )
        return None
    if finished > cutoff:
        _logger.info(
            "Session finished %s, after the %s cutoff; no exemption", finished, cutoff
        )
        return None
    return _at(record.date, SESSION_COMPLETED_UNTIL)


def to_entry(
    record: SessionRecord | None,
    *,
    today: str,
    refreshed_at: float,
    alarm: tuple[int, int] | None = None,
) -> dict[str, object]:
    """The unsigned file body for ``record`` (today's) or the ``none`` entry.

    ``alarm`` is the phone's alarm time; with no session yet the day is
    exempt until that plus ``SESSION_NONE_GRACE``. None means "unknown",
    which grants nothing -- fail closed.
    """
    if record is None:
        entry: dict[str, object] = {
            "date": today,
            "outcome": NONE_OUTCOME,
            "started_at": None,
            "finished_at": None,
            "energy": None,
            "weight_kg": None,
            "re_rings": 0,
            "device_id": "",
            "published_at": None,
            "refreshed_at": refreshed_at,
        }
        if alarm is not None:
            entry["exempt_until"] = (_at(today, alarm) + SESSION_NONE_GRACE).isoformat()
        return entry
    entry = {
        "date": record.date,
        "outcome": record.outcome,
        "started_at": record.started_at,
        "finished_at": record.finished_at,
        "energy": record.energy,
        "weight_kg": record.weight_kg,
        "re_rings": record.re_rings,
        "device_id": record.device_id,
        "published_at": record.published_at,
        "refreshed_at": refreshed_at,
    }
    until = exempt_until(record)
    if until is not None:
        entry["exempt_until"] = until.isoformat()
    return entry
