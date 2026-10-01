"""The stick-day checks: penalty and lockdown, keyed by the day *judged*.

The phone's ``stick_check`` carries ``data.date`` -- the morning it judged.
A boot or watchdog check catches up to five past days, so a Tuesday can be
judged on Thursday; keying by the event's ``at`` would pin that verdict on
the wrong morning. Verdict ``miss`` is the phone's miss; with no
``stick_check`` for the day, ``stick_state.last_miss`` stands in.

A lockdown follows the check that found the miss, so it is expected on the
*judging* day. A miss caught up after its lockdown would already have ended
sends nothing (the phone's own rule), so a late judgement without a
``lockdown_sent`` is noted, not flagged.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from wake_alarm._audit_evidence import (
    bad,
    na,
    ok,
    pc_on_day,
    phone_kinds,
    phone_on_day,
)
from wake_alarm._enforcement_payload import is_honoured
from wake_alarm._enforcement_records import parse_instant

if TYPE_CHECKING:
    from datetime import date

    from wake_alarm._audit_evidence import Check, Evidence
    from wake_alarm._enforcement_records import PhoneEvent

MISS = "miss"
_PROVISIONAL = "too_early"


def verdicts(ev: Evidence) -> list[PhoneEvent]:
    """``stick_check`` events that judged the audited day, final ones only."""
    day = ev.day.isoformat()
    return [
        e
        for e in ev.phone
        if e.kind == "stick_check"
        and e.data.get("date") == day
        and e.data.get("verdict") != _PROVISIONAL
    ]


def miss_judged_on(ev: Evidence) -> date | None:
    """The day the phone judged this morning a miss, if it did.

    Falls back to ``stick_state.last_miss`` (judged that same day, as far as
    can be told) when no ``stick_check`` for the day was published.
    """
    for event in verdicts(ev):
        if event.data.get("verdict") == MISS:
            at = parse_instant(event.at)
            return at.date() if at is not None else ev.day
    state = ev.stick_state
    if state is not None and state.last_miss == ev.day.isoformat():
        return ev.day
    return None


def _escaped(ev: Evidence) -> bool:
    """Whether an honoured escape excuses the audited day."""
    return any(is_honoured(e) for e in ev.escapes)


def check_penalty(ev: Evidence) -> Check:
    """The PC penalty agrees with the outcome and any escape."""
    name = "penalty consistent"
    escaped = _escaped(ev)
    if escaped and ev.penalty_issued == ev.day.isoformat():
        return bad(name, "escaped, but the penalty is on disk")
    if escaped:
        return ok(name, "escaped: no penalty")
    if not ev.stick_day or ev.free_day:
        return na(name, "not a stick day")
    written = pc_on_day(ev, "penalty_written")
    if miss_judged_on(ev) is not None and not written:
        return bad(name, "phone counted a miss, PC wrote none")
    return ok(name, "penalty written" if written else "no miss, no penalty")


def _sent_on(ev: Evidence, judged: date) -> list[PhoneEvent]:
    """``lockdown_sent`` events stamped on the judging day."""
    sent: list[PhoneEvent] = []
    for event in ev.phone:
        at = parse_instant(event.at)
        if event.kind == "lockdown_sent" and at is not None and at.date() == judged:
            sent.append(event)
    return sent


def _lockdown_for_miss(ev: Evidence, judged: date) -> Check:
    """The lockdown the miss judged on ``judged`` should have sent."""
    name = "lockdown consistent"
    sent = _sent_on(ev, judged)
    if not sent:
        if judged > ev.day:
            return ok(name, f"miss caught up on {judged}; lockdown may have expired")
        return bad(name, "phone judged a miss, no lockdown_sent")
    state = ev.stick_state
    until = sent[-1].data.get("until")
    if (
        state is not None
        and state.last_miss == ev.day.isoformat()
        and until != state.locked_through
    ):
        return bad(
            name,
            f"lockdown_sent until {until}, "
            f"stick_state locked_through {state.locked_through}",
        )
    return ok(name, f"until {until}")


def check_lockdown(ev: Evidence) -> Check:
    """``lockdown_sent`` agrees with the verdict, and escapes lift it."""
    name = "lockdown consistent"
    judged = miss_judged_on(ev)
    sent_today = [e for e in phone_on_day(ev) if e.kind == "lockdown_sent"]
    if _escaped(ev) and sent_today:
        if "lift_sent" not in phone_kinds(ev):
            return bad(name, "escaped, but no lift_sent")
        return ok(name, "lifted after the escape")
    if judged is not None:
        return _lockdown_for_miss(ev, judged)
    if sent_today and not _escaped(ev):
        return bad(name, "lockdown_sent without a recorded miss")
    return na(name, "no miss")
