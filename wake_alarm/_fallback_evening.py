"""The fallback timer's 21:00 hour: ring when the phone's notifications are off.

``_fallback.tick`` hands every 21:xx tick here before any morning code runs,
so the morning rules (today free or sick, the window, the morning latch) never
see the evening and the evening never sees them. The rule itself is
``_evening_policy``; this module gathers its facts, rings and logs.

Events use their own names (``evening_tick``, ``evening_ring_start``,
``evening_ring_stop``) so the morning audit never counts an evening ring as
the morning's. An unreachable Firebase at a tick rings nothing (no event is
known); one during a ring keeps ringing, bounded by the cap.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import freedays

from wake_alarm._constants import EVENING_RING_FILE
from wake_alarm._enforcement_payload import enforcement_view
from wake_alarm._evening_policy import (
    FREE_TOMORROW,
    NOTIFICATIONS_OFF,
    SICK_TOMORROW,
    EveningFacts,
    decide,
    needs_fetch,
    stop_reason,
)
from wake_alarm._events import emit, emit_on_change
from wake_alarm._fallback_latch import Latch, mark_started, mark_stopped, read_latch
from wake_alarm._fallback_ring import ring
from wake_alarm._ring_wav import SYSTEM_WAV_DIR, USER_WAV_DIR, ensure_pair
from wake_alarm._sick import alarm_stands_down, alarm_stands_down_synced
from wake_alarm._sync_transport import fetch_firebase_logs

if TYPE_CHECKING:
    from wake_alarm._fallback_policy import Decision

TERMINATED = "terminated"


def _now() -> datetime:
    """Aware local now; the seam tests patch."""
    return datetime.now(tz=UTC).astimezone()


def _tomorrow_off(now: datetime, *, sync: bool) -> str | None:
    """Why tomorrow rings nothing, or None; pulls the sick pool when acting."""
    tomorrow = now.date() + timedelta(days=1)
    if freedays.is_free_day(tomorrow):
        return FREE_TOMORROW
    sick = alarm_stands_down_synced if sync else alarm_stands_down
    return SICK_TOMORROW if sick(tomorrow) else None


def observe_evening(now: datetime, *, sync: bool) -> EveningFacts:
    """Gather the evening's facts; Firebase only when it can change them."""
    day = now.date().isoformat()
    facts = EveningFacts(
        now=now,
        tomorrow_off=_tomorrow_off(now, sync=sync),
        latch=read_latch(day, EVENING_RING_FILE),
    )
    if not needs_fetch(facts):
        return facts
    published = fetch_firebase_logs()
    if published is None:
        return replace(facts, reachable=False)
    return replace(
        facts, off_since=enforcement_view(published).notifications_off_since(day)
    )


def _poll(off_since: datetime | None) -> str | None:
    """Re-observe while ringing; the reason to stop, or None.

    An unreachable Firebase keeps the off state the ring started with: fail
    toward ringing, never toward silence. The cap still ends it.
    """
    facts = observe_evening(_now(), sync=True)
    if not facts.reachable:
        facts = replace(facts, off_since=off_since, reachable=True)
    return stop_reason(facts)


def _close(latch: Latch, reason: str) -> None:
    """Stop an open evening latch and log it."""
    stopped = mark_stopped(
        latch, now=_now(), stop_reason=reason, file=EVENING_RING_FILE
    )
    emit(
        "evening_ring_stop",
        reason,
        stop_reason=reason,
        started_at=stopped.started_at,
        stopped_at=stopped.stopped_at,
    )


def ring_evening(facts: EveningFacts) -> str:
    """Latch, ring until a stop condition, unlatch; returns the stop reason."""
    day = facts.now.date().isoformat()
    resumed = facts.latch is not None and facts.latch.started_at is not None
    latch = mark_started(
        facts.latch,
        day=day,
        now=facts.now,
        reason=NOTIFICATIONS_OFF,
        file=EVENING_RING_FILE,
    )
    off_since = facts.off_since
    emit(
        "evening_ring_start",
        NOTIFICATIONS_OFF,
        reason=NOTIFICATIONS_OFF,
        resumed=resumed,
        off_since=off_since.isoformat() if off_since else None,
        started_at=latch.started_at,
    )
    stopped = TERMINATED
    try:
        # Inside the try, as in the morning: a WAV that cannot be generated
        # must still close the latch.
        rise, loop = ensure_pair(SYSTEM_WAV_DIR, USER_WAV_DIR)
        stopped = ring(lambda: _poll(off_since), rise=rise, loop=loop)
    finally:
        _close(latch, stopped)
    return stopped


def evening_tick(now: datetime) -> Decision:
    """One 21:xx timer tick: observe, log a changed decision, ring if due."""
    facts, day = observe_evening(now, sync=True), now.date().isoformat()
    decision = decide(facts)
    emit_on_change(
        "evening_tick",
        f"{day}|{decision.ring}|{decision.reason}",
        f"{'ring' if decision.ring else 'quiet'}: {decision.reason}",
        ring=decision.ring,
        reason=decision.reason,
        reachable=facts.reachable,
    )
    latch = facts.latch
    if decision.ring:
        ring_evening(facts)
    elif latch is not None and latch.started_at and not latch.stopped_at:
        _close(latch, decision.reason)
    return decision


def evening_dry_run(now: datetime) -> str:
    """The ``--dry-run`` report for a 21:xx instant; writes nothing."""
    facts = observe_evening(now, sync=False)
    decision = decide(facts)
    verdict = "WOULD RING" if decision.ring else "quiet"
    return (
        f"{now:%Y-%m-%d %H:%M} — {verdict}: {decision.reason}\n"
        f"  evening check: tomorrow_off={facts.tomorrow_off} "
        f"firebase={'ok' if facts.reachable else 'UNREACHABLE'}\n"
        f"  off_since={facts.off_since}\n"
        f"  latch={facts.latch}\n"
    )
