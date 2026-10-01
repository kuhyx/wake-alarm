"""The PC fallback alarm's rule, as one pure function.

``DOCS-wake-enforcement.md``'s table, first match wins, inside
``A - 5 min .. A + 45 min`` on a day that is not free:

=========================================================  ==================
escape recorded for today, or a session started today      do not ring / stop
ring already ran 30 min today (``FALLBACK_RING_CAP``)       never again today
``now >= A + 2 min`` and no ``ring_started`` for today      ring: phone_silent
``now >= A + 15 min`` (``SESSION_NONE_GRACE``)              ring: no_session
=========================================================  ==================

The window gates *starting* a ring only. A ring that already started today
and has not hit its cap is judged by the table alone, so a ringing process
killed by a hibernate resumes after the resume instead of going quiet
because the clock moved past the window. Firebase being unreachable is
modelled by the caller as "no ping, no session, no escape": fail toward
ringing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING

from wake_alarm._constants import (
    FALLBACK_ALARM_HOUR,
    FALLBACK_PHONE_SILENT_AFTER,
    FALLBACK_RING_CAP,
    FALLBACK_WINDOW_END,
    SESSION_NONE_GRACE,
)

if TYPE_CHECKING:
    from wake_alarm._fallback_latch import Latch
    from wake_alarm._sync import Alarm

# The tick starts looking (and fetching) this long before the alarm, so the
# first decision of the day is logged before anything can ring.
FALLBACK_WINDOW_START: timedelta = timedelta(minutes=5)

# While ringing, how often the stop conditions are re-read from Firebase.
FALLBACK_POLL_SECONDS: float = 20.0

# Reasons, as they appear in events.jsonl and fallback_ring.json.
FREE_DAY = "free_day"
OUTSIDE_WINDOW = "outside_window"
ESCAPE = "escape"
SESSION_STARTED = "session_started"
CAP = "cap"
PHONE_SILENT = "phone_silent"
NO_SESSION = "no_session"
WAITING = "waiting"

# Once seen, these hold for the rest of the day even if Firebase later stops
# answering: an unreachable backend fails toward ringing, but never toward
# ringing at someone already known to be up.
FINAL_REASONS: frozenset[str] = frozenset({ESCAPE, SESSION_STARTED, CAP})


@dataclass(frozen=True)
class Facts:
    """Everything one decision needs; the caller gathers it.

    ``settled`` is a final reason (``FINAL_REASONS``) already seen today.
    """

    now: datetime
    alarm_at: datetime
    free_day: bool
    escaped: bool = False
    session_started: bool = False
    ring_started: bool = False
    latch: Latch | None = None
    settled: str | None = None


@dataclass(frozen=True)
class Decision:
    """Ring or not, and the one-word reason either way."""

    ring: bool
    reason: str


def alarm_instant(alarm: Alarm, day: date) -> datetime:
    """Today's ``A``: the alarm on ``day``, clamped to the 08:00 baseline.

    Built naive and localised afterwards, like ``_trigger._fire_window``, so
    the offset is the one in force at the alarm, not at the tick.
    """
    hour, minute = min((alarm.hour, alarm.minute), (FALLBACK_ALARM_HOUR, 0))
    return datetime.combine(day, time(hour, minute)).astimezone()


def _ring_started_today(latch: Latch | None) -> bool:
    """Whether today's fallback has already rung at all."""
    return latch is not None and latch.started() is not None


def needs_facts(now: datetime, alarm_at: datetime, latch: Latch | None) -> bool:
    """Whether this tick must fetch the phone's state at all.

    Outside the window with nothing rung today the answer is already
    ``outside_window``, so the per-minute tick stays off the network.
    """
    if _ring_started_today(latch):
        return True
    return alarm_at - FALLBACK_WINDOW_START <= now < alarm_at + FALLBACK_WINDOW_END


def is_capped(facts: Facts) -> bool:
    """Whether today's ring has used its 30 minutes."""
    latch = facts.latch
    if latch is None:
        return False
    if latch.stop_reason == CAP:
        return True
    started = latch.started()
    return started is not None and facts.now >= started + FALLBACK_RING_CAP


def stop_reason(facts: Facts) -> str | None:
    """Why a ring in progress must stop now, or None to keep ringing.

    Only the contract's three stop conditions (plus a day that turned free):
    a phone that comes back on mid-ring does not silence the PC -- getting up
    does.
    """
    if facts.free_day:
        return FREE_DAY
    if facts.settled in FINAL_REASONS:
        return facts.settled
    if facts.escaped:
        return ESCAPE
    if facts.session_started:
        return SESSION_STARTED
    if is_capped(facts):
        return CAP
    return None


def decide(facts: Facts) -> Decision:
    """The table above; first match wins."""
    if facts.free_day:
        return Decision(ring=False, reason=FREE_DAY)
    if not needs_facts(facts.now, facts.alarm_at, facts.latch):
        return Decision(ring=False, reason=OUTSIDE_WINDOW)
    stop = stop_reason(facts)
    if stop is not None:
        return Decision(ring=False, reason=stop)
    if facts.now >= facts.alarm_at + FALLBACK_PHONE_SILENT_AFTER and not (
        facts.ring_started
    ):
        return Decision(ring=True, reason=PHONE_SILENT)
    if facts.now >= facts.alarm_at + SESSION_NONE_GRACE:
        return Decision(ring=True, reason=NO_SESSION)
    return Decision(ring=False, reason=WAITING)
