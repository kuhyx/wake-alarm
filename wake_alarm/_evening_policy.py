"""The 21:00 notifications check's rule, as pure functions (``DOCS-bypass.md``).

Switching off "All WakeAlarm notifications" silences the ring and no device
policy can lock that switch, so the phone reports the state as a
``notifications`` phone event (at 21:00 and whenever the switch moves) and
the PC rings in the evening, while there is still time to fix it:

=============================================  ===================
outside 21:00-21:59                            start nothing
tomorrow is a free or sick day                 never ring
the evening ring used its 30 minutes           never again tonight
today's newest event says on, or none today    quiet
otherwise                                      ring: notifications_off
=============================================  ===================

Tomorrow, not today: the point is tomorrow's alarm. The hour gates
*starting* only; a ring in progress is judged by :func:`stop_reason`, so one
started at 21:50 runs its full 30 minutes. The cap is measured from the
evening latch's first start, never the morning's or a bypass's.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from wake_alarm._fallback_policy import CAP, Decision, latch_capped

if TYPE_CHECKING:
    from datetime import datetime

    from wake_alarm._fallback_latch import Latch

EVENING_HOUR: int = 21

# Reasons, as they appear in events.jsonl and evening_ring.json.
NOTIFICATIONS_OFF = "notifications_off"
NOTIFICATIONS_ON = "notifications_on"
OUTSIDE_EVENING = "outside_evening"
FREE_TOMORROW = "free_tomorrow"
SICK_TOMORROW = "sick_tomorrow"
UNREACHABLE = "firebase_unreachable"


@dataclass(frozen=True)
class EveningFacts:
    """Everything one evening decision needs; the caller gathers it.

    ``off_since`` is today's newest ``notifications`` event when it says
    off; ``tomorrow_off`` is :data:`FREE_TOMORROW` / :data:`SICK_TOMORROW`.
    """

    now: datetime
    tomorrow_off: str | None = None
    off_since: datetime | None = None
    latch: Latch | None = None
    reachable: bool = True


def in_evening(now: datetime) -> bool:
    """Whether ``now`` is in the hour that may start an evening ring."""
    return now.hour == EVENING_HOUR


def is_capped(facts: EveningFacts) -> bool:
    """Whether tonight's ring has used its 30 minutes."""
    return latch_capped(facts.latch, facts.now)


def needs_fetch(facts: EveningFacts) -> bool:
    """Whether the phone's events can still change the answer."""
    return facts.tomorrow_off is None and not is_capped(facts)


def stop_reason(facts: EveningFacts) -> str | None:
    """Why an evening ring must stop (or not start), or None to ring."""
    if facts.tomorrow_off is not None:
        return facts.tomorrow_off
    if is_capped(facts):
        return CAP
    if facts.off_since is None:
        return NOTIFICATIONS_ON if facts.reachable else UNREACHABLE
    return None


def decide(facts: EveningFacts) -> Decision:
    """Ring or not at an evening tick; the table above, first match wins."""
    if not in_evening(facts.now):
        return Decision(ring=False, reason=OUTSIDE_EVENING)
    stop = stop_reason(facts)
    if stop is not None:
        return Decision(ring=False, reason=stop)
    return Decision(ring=True, reason=NOTIFICATIONS_OFF)
