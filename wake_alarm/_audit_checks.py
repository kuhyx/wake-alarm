"""Expected-vs-observed for one morning: pure, evidence in, checks out.

Each check is ``ok`` (True), a mismatch (False) or not applicable (None).
Escapes and mismatches become the report's ``## Flags`` -- escapes first,
because every use of the hatch must be seen.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from wake_alarm._audit_evidence import (
    Check,
    Evidence,
    bad,
    na,
    ok,
    pc_on_day,
    phone_on_day,
)
from wake_alarm._audit_stick import check_lockdown, check_penalty
from wake_alarm._constants import RTC_WAKE_LEAD
from wake_alarm._enforcement_payload import is_honoured
from wake_alarm._enforcement_records import parse_instant

if TYPE_CHECKING:
    from datetime import date, datetime

    from wake_alarm._audit_sources import PcEvent

_FINAL_STOPS = frozenset({"escape", "session_started", "cap", "free_day"})
_RING_KINDS = frozenset({"ring_screen_opened", "ring_started_published"})
# alarm_fired.data.reason: only the daily ring is the morning's ring -- a
# free_day firing rings nothing, and a rering presupposes an earlier ring.
_NOT_THE_MORNING_RING = frozenset({"free_day", "rering"})


def alarm_from_events(pc: list[PcEvent], day: date) -> datetime | None:
    """The ``A`` the fallback tick used on ``day``, if it ran."""
    for event in pc:
        alarm = event.fields.get("alarm")
        if event.event == "fallback_tick" and isinstance(alarm, str):
            at = parse_instant(alarm)
            if at is not None and at.date() == day:
                return at
    return None


def check_alarm(ev: Evidence) -> Check:
    """The alarm for the day is known."""
    if ev.alarm_at is None:
        return bad("alarm known", "no alarm time known for this day")
    return ok("alarm known", f"{ev.alarm_at:%H:%M} ({ev.alarm_source})")


def check_rtc(ev: Evidence) -> Check:
    """On a stick day the RTC was armed the night before."""
    if not ev.stick_day or ev.free_day:
        return na("RTC armed the night before", "not a stick day")
    armed = [
        e
        for e in ev.pc
        if e.event == "rtc_armed" and e.fields.get("target_date") == ev.day.isoformat()
    ]
    if not armed:
        return bad("RTC armed the night before", "no rtc_armed for this day")
    return ok(
        "RTC armed the night before",
        f"{armed[-1].fields.get('wake_at')} (logged {armed[-1].at:%H:%M})",
    )


def check_up_by_alarm(ev: Evidence) -> Check:
    """On a stick day the PC was up by ``A``."""
    if not ev.stick_day or ev.free_day or ev.alarm_at is None:
        return na("PC up by A", "not a stick day or no alarm")
    alarm = ev.alarm_at
    lead = alarm - RTC_WAKE_LEAD - timedelta(minutes=5)
    ups = [u for u in ev.ups if u.at.date() == ev.day and u.at <= alarm]
    if ups:
        return ok("PC up by A", f"{ups[-1].kind} at {ups[-1].at:%H:%M:%S}")
    alive = [at for at in ev.pc_seen if lead <= at <= alarm]
    if alive:
        return ok("PC up by A", f"already up (logged at {alive[0]:%H:%M})")
    return bad("PC up by A", f"no boot, resume or PC event by {alarm:%H:%M}")


def check_ring(ev: Evidence) -> Check:
    """Something rang: the phone's ring screen, or the PC fallback."""
    if ev.free_day:
        return na("something rang", "free day")
    fallback = pc_on_day(ev, "fallback_ring_start")
    phone = ev.ring_started or any(
        e.kind in _RING_KINDS
        or (
            e.kind == "alarm_fired"
            and e.data.get("reason") not in _NOT_THE_MORNING_RING
        )
        for e in phone_on_day(ev)
    )
    if not (phone or fallback):
        return bad("something rang", "no ring_started and no fallback ring")
    parts = (["phone"] if phone else []) + (["PC fallback"] if fallback else [])
    return ok("something rang", " + ".join(parts))


def check_fallback_stop(ev: Evidence) -> Check:
    """Every fallback ring stopped, and for a contract reason."""
    starts = pc_on_day(ev, "fallback_ring_start")
    if not starts:
        return na("fallback stopped correctly", "fallback did not ring")
    stops = pc_on_day(ev, "fallback_ring_stop")
    reasons = [str(e.fields.get("stop_reason")) for e in stops]
    if len(stops) < len(starts) or (reasons and reasons[-1] not in _FINAL_STOPS):
        return bad(
            "fallback stopped correctly",
            f"{len(starts)} start(s), stops: {', '.join(reasons) or 'none'}",
        )
    return ok("fallback stopped correctly", ", ".join(reasons))


CHECKS = (
    check_alarm,
    check_rtc,
    check_up_by_alarm,
    check_ring,
    check_fallback_stop,
    check_penalty,
    check_lockdown,
)


def run_checks(ev: Evidence) -> list[Check]:
    """Every check, in report order."""
    return [check(ev) for check in CHECKS]


def flags(ev: Evidence, checks: list[Check]) -> list[str]:
    """Escapes first, then every mismatch."""
    lines = []
    for escape in ev.escapes:
        honoured = "" if is_honoured(escape) else " (IGNORED by the PC: "
        if honoured:
            honoured += "after the last day or reason too short)"
        lines.append(f"ESCAPE {escape.at or escape.date}: {escape.reason!r}{honoured}")
    lines.extend(f"MISMATCH {c.name}: {c.detail}" for c in checks if c.ok is False)
    return lines
