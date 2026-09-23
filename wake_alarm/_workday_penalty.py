"""Tue/Wed/Thu miss -> tomorrow loses its usual leniency.

The no-lock carrot (``_session_policy``) only motivates finishing the
morning when the PC is around to enjoy it -- true on a weekend, false on a
workday, since the user leaves for work regardless of whether the PC is
locked. On Tuesday/Wednesday/Thursday -- the same set screen-locker calls
"relaxed" (``_weekly_check.is_relaxed_day``) and leetcode-guard prices as
cheap (``Pricing.doubled_days``) -- a miss instead costs tomorrow's leniency
in both, so skipping is never free just because nobody is home to notice.

Distinct from ``morning_session.json``: that file always describes *today*
and is overwritten at the date rollover, so it cannot carry a marker forward
to tomorrow. This file's only field a consumer checks is ``penalty_date``:
today == penalty_date means "no leniency today," the same shape as
``morning_session.json``'s own ``exempt_until`` predicate.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
import json
import logging

import freedays
from gatelock.log_integrity import compute_entry_hmac

from wake_alarm._constants import STICK_DAYS, WORKDAY_PENALTY_FILE
from wake_alarm._session_policy import NONE_OUTCOME

_logger = logging.getLogger(__name__)


def is_stick_day(day: date) -> bool:
    """Tuesday/Wednesday/Thursday -- the same set already treated as lenient."""
    return day.weekday() in STICK_DAYS


def is_workday_miss(entry: dict[str, object], now: datetime) -> bool:
    """Whether today's session entry is a genuine miss, not just late.

    ``failed`` is always a miss. ``none`` is only a miss once its own grace
    has expired -- before that the morning could still start. A late
    ``completed`` (the walk happened, just after the carrot's cutoff) is
    deliberately not a miss: the goal was waking up, and that happened.
    """
    outcome = entry.get("outcome")
    if outcome == "failed":
        return True
    if outcome != NONE_OUTCOME:
        return False
    until = entry.get("exempt_until")
    if not isinstance(until, str):
        return False
    try:
        return now >= datetime.fromisoformat(until)
    except ValueError:
        return False


def penalty_entry(*, today: date) -> dict[str, object]:
    """The unsigned body: tomorrow loses its leniency."""
    return {
        "penalty_date": (today + timedelta(days=1)).isoformat(),
        "issued_date": today.isoformat(),
    }


def write_penalty(entry: dict[str, object]) -> bool:
    """Sign and write ``entry``; False when the disk refused."""
    signature = compute_entry_hmac(entry)
    if signature is not None:
        entry["hmac"] = signature
    else:
        _logger.warning("HMAC key unavailable — writing unsigned workday penalty")
    try:
        WORKDAY_PENALTY_FILE.parent.mkdir(parents=True, exist_ok=True)
        WORKDAY_PENALTY_FILE.write_text(json.dumps(entry, indent=2))
    except OSError as exc:
        _logger.warning("Could not write %s: %s", WORKDAY_PENALTY_FILE, exc)
        return False
    return True


def maybe_apply(entry: dict[str, object], now: datetime) -> bool:
    """Write tomorrow's penalty when today is a missed stick-day; else no-op.

    Best-effort: never raises, since the per-refresh caller must not fail on
    this. A free day is never penalised even if unsynced state elsewhere
    would otherwise have rung the alarm -- the pool is fail-closed the other
    direction (a corrupt read is "not free"), which is exactly what is
    wanted here too: an unreadable pool means no penalty, never a spurious
    one.
    """
    if freedays.is_free_day(now.date()) or not is_stick_day(now.date()):
        return False
    if not is_workday_miss(entry, now):
        return False
    return write_penalty(penalty_entry(today=now.date()))
