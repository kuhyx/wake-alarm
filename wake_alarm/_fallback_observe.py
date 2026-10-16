"""One look at the world for the fallback alarm, and its bookkeeping.

Split from ``_fallback`` (tick, ring lifecycle, CLI): this is "what is true
right now" -- today's alarm, the latch, the free-day and sick-day pools
and, only when the decision needs it, every device's ``alarm.json``.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

import freedays

from wake_alarm._enforcement_payload import EnforcementView, enforcement_view
from wake_alarm._escapes import note_escapes
from wake_alarm._events import emit_on_change, last_value, remember
from wake_alarm._fallback_latch import Latch, read_latch
from wake_alarm._fallback_policy import (
    FINAL_REASONS,
    Facts,
    alarm_instant,
    needs_facts,
)
from wake_alarm._session_payload import newest_session
from wake_alarm._sick import alarm_stands_down, alarm_stands_down_synced
from wake_alarm._sync import get_alarm
from wake_alarm._sync_transport import fetch_firebase_logs

if TYPE_CHECKING:
    from datetime import datetime

SETTLED_SLOT = "fallback_settled"


@dataclass(frozen=True)
class Observation:
    """One look at the world: the facts, and whether Firebase answered."""

    facts: Facts
    reachable: bool = True
    view: EnforcementView | None = None


def settled_reason(day: str, latch: Latch | None) -> str | None:
    """A final reason already seen today, from the latch or the event state."""
    if latch is not None and latch.stop_reason in FINAL_REASONS:
        return latch.stop_reason
    remembered = (last_value(SETTLED_SLOT) or "").partition("|")
    return remembered[2] if remembered[0] == day and remembered[2] else None


def _sick_today(now: datetime, *, online: bool, sync: bool) -> bool:
    """Whether today is a sick day; pulls the pool first when acting online.

    Synced only on the ticks that already go to the network (the window, or
    a ring in progress), so a day marked sick on the phone mid-ring stops
    the ring at the next poll, and an off-window tick stays local.
    """
    if online and sync:
        return alarm_stands_down_synced(now.date())
    return alarm_stands_down(now.date())


def observe(now: datetime, *, sync: bool) -> Observation:
    """Gather the facts; the network only when the decision needs it.

    ``sync`` is False for ``--dry-run``: pulling the sick-day pool rewrites
    its local file, and a dry run writes nothing.
    """
    day = now.date().isoformat()
    latch = read_latch(day)
    alarm_at = alarm_instant(get_alarm(), now.date())
    online = needs_facts(now, alarm_at, latch)
    facts = Facts(
        now=now,
        alarm_at=alarm_at,
        free_day=freedays.is_free_day(now.date()),
        sick_day=_sick_today(now, online=online, sync=sync),
        latch=latch,
        settled=settled_reason(day, latch),
    )
    if facts.free_day or facts.sick_day or not online:
        return Observation(facts)
    published = fetch_firebase_logs()
    if published is None:
        return Observation(facts, reachable=False)
    view = enforcement_view(published)
    session = newest_session(published)
    return Observation(
        replace(
            facts,
            escaped=view.escape_for(day) is not None,
            session_started=session is not None and session.date == day,
            ring_started=view.ring_started_on(day),
        ),
        view=view,
    )


def record(seen: Observation) -> None:
    """Log what this observation means for the PC's own state."""
    day = seen.facts.now.date().isoformat()
    if seen.reachable:
        remember("firebase_unreachable", None)
    else:
        emit_on_change(
            "firebase_unreachable",
            day,
            "treating as no ping, no session",
            alarm=seen.facts.alarm_at.isoformat(),
        )
    if seen.view is not None:
        note_escapes(seen.view)


def remember_final(day: str, reason: str) -> None:
    """Make a final reason stick for the rest of the day."""
    if reason in FINAL_REASONS:
        remember(SETTLED_SLOT, f"{day}|{reason}")
