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

An escape (``DOCS-wake-enforcement.md``) for a morning means no penalty is
written for it, and one already issued that day is deleted. A sick day
(``_sick``) is the same, for its own reason: nothing is written on a sick
day, and a penalty *issued* on a day marked sick afterwards (a miss at 08:15,
"sick" at 14:00) is deleted by the next ``--refresh`` or RTC tick. Other
readers must not wait for that: see ``DOCS-wake-enforcement.md``.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
import json
import logging

import freedays
from gatelock.log_integrity import compute_entry_hmac

from wake_alarm._constants import WORKDAY_PENALTY_FILE
from wake_alarm._events import emit
from wake_alarm._session_policy import NONE_OUTCOME
from wake_alarm._sick import is_sick, is_sick_synced

_logger = logging.getLogger(__name__)


def is_stick_day(day: date) -> bool:
    """Tuesday/Wednesday/Thursday: ``freedays.WORKDAYS``, the shared set."""
    return freedays.is_workday(day)


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


def issued_date() -> str | None:
    """``issued_date`` of the penalty on disk, or None when there is none."""
    try:
        raw = json.loads(WORKDAY_PENALTY_FILE.read_text())
    except OSError, ValueError:
        return None
    issued = raw.get("issued_date") if isinstance(raw, dict) else None
    return issued if isinstance(issued, str) else None


def _cancel(issued: str, cause: str) -> bool:
    """Delete the penalty issued on ``issued``; log ``penalty_cancelled``."""
    try:
        WORKDAY_PENALTY_FILE.unlink()
    except OSError as exc:
        _logger.warning("Could not cancel %s: %s", WORKDAY_PENALTY_FILE, exc)
        return False
    emit(
        "penalty_cancelled",
        f"{cause.replace('_', ' ')} for {issued}",
        issued_date=issued,
        cause=cause,
    )
    return True


def cancel_for_escapes(escaped_dates: frozenset[str]) -> bool:
    """Delete the penalty when an escape excuses the morning it was issued.

    Returns:
        True when a penalty was removed.
    """
    issued = issued_date()
    if issued is None or issued not in escaped_dates:
        return False
    return _cancel(issued, "escape")


def cancel_for_sick_day() -> bool:
    """Delete the penalty when the morning it was issued is now a sick day.

    Local pool only: callers on a timer keep it fresh. Fail closed -- an
    unreadable pool or date keeps the penalty.

    Returns:
        True when a penalty was removed.
    """
    issued = issued_date()
    if issued is None:
        return False
    try:
        day = date.fromisoformat(issued)
    except ValueError:
        return False
    return is_sick(day) and _cancel(issued, "sick_day")


def skip_reason(
    entry: dict[str, object],
    now: datetime,
    *,
    escaped_dates: frozenset[str] = frozenset(),
) -> str | None:
    """Why today earns no penalty, or None when it does. Pure and local."""
    today = now.date()
    if today.isoformat() in escaped_dates:
        return "escaped"
    if freedays.is_free_day(today):
        return "free day"
    if not is_stick_day(today):
        return "not a stick day"
    if is_sick(today):
        return "sick day"
    if not is_workday_miss(entry, now):
        return "no miss"
    return None


def maybe_apply(
    entry: dict[str, object],
    now: datetime,
    *,
    escaped_dates: frozenset[str] = frozenset(),
) -> bool:
    """Write tomorrow's penalty when today is a missed stick-day; else no-op.

    Best-effort: never raises, since the per-refresh caller must not fail on
    this. A free day is never penalised even if unsynced state elsewhere
    would otherwise have rung the alarm -- the pool is fail-closed the other
    direction (a corrupt read is "not free"), which is exactly what is
    wanted here too: an unreadable pool means no penalty, never a spurious
    one. An escaped morning or a sick day is never penalised either; the
    sick-day pool is pulled once more before the day's *first* write, so a
    day marked sick on the phone minutes ago still counts.

    ``penalty_written`` is logged once per issued day, not on every
    two-minute refresh that rewrites the same entry.
    """
    if skip_reason(entry, now, escaped_dates=escaped_dates) is not None:
        return False
    today = now.date()
    previously = issued_date()
    if previously != today.isoformat() and is_sick_synced(today):
        return False
    entry_body = penalty_entry(today=today)
    if not write_penalty(entry_body):
        return False
    if previously != today.isoformat():
        emit(
            "penalty_written",
            f"penalty for {entry_body['penalty_date']}",
            penalty_date=entry_body["penalty_date"],
            issued_date=entry_body["issued_date"],
            outcome=entry.get("outcome"),
        )
    return True
