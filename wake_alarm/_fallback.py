"""The PC fallback alarm: one per-minute tick, 04:00-09:59.

``wake-alarm-fallback.timer`` runs ``--tick`` every minute. Outside
``A - 5 min .. A + 45 min`` (or on a free day) a tick decides from local
state alone and never touches the network. Inside, it reads every device's
``alarm.json`` once, decides (``_fallback_policy.decide``) and, when the
decision is to ring, rings *in this process* until a stop condition holds
-- the unit is a oneshot, so the timer's next minute is a no-op while it
rings and no PID file is needed. Firebase unreachable counts as "no ping,
no session, no escape": fail toward ringing.

    python -m wake_alarm._fallback --tick      # what the timer runs
    python -m wake_alarm._fallback --dry-run   # decide now, change nothing
    python -m wake_alarm._fallback --show      # latch + last decision, offline
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
import signal
import sys
from typing import TYPE_CHECKING

import freedays

from wake_alarm._cli_modes import mode_parser, parse_with_now
from wake_alarm._events import emit, emit_on_change, last_value
from wake_alarm._fallback_latch import Latch, mark_started, mark_stopped, read_latch
from wake_alarm._fallback_observe import (
    Observation,
    observe,
    record,
    remember_final,
    settled_reason,
)
from wake_alarm._fallback_policy import (
    Decision,
    Facts,
    alarm_instant,
    decide,
    stop_reason,
)
from wake_alarm._fallback_ring import ring
from wake_alarm._logging_setup import configure_logging
from wake_alarm._ring_wav import SYSTEM_WAV_DIR, USER_WAV_DIR, ensure_pair
from wake_alarm._sync import get_alarm

if TYPE_CHECKING:
    from types import FrameType

TERMINATED = "terminated"


def _now() -> datetime:
    """Aware local now; the seam tests patch."""
    return datetime.now(tz=UTC).astimezone()


def _close(latch: Latch, reason: str) -> None:
    """Stop an open latch and log it."""
    stopped = mark_stopped(latch, now=_now(), stop_reason=reason)
    emit(
        "fallback_ring_stop",
        reason,
        stop_reason=reason,
        started_at=stopped.started_at,
        stopped_at=stopped.stopped_at,
    )


def _poll(day: str) -> str | None:
    """Re-observe while ringing; the reason to stop, or None."""
    seen = observe(_now())
    record(seen)
    reason = stop_reason(replace(seen.facts, latch=read_latch(day)))
    if reason is not None:
        remember_final(day, reason)
    return reason


def ring_now(facts: Facts, reason: str) -> str:
    """Latch, ring until a stop condition, unlatch; returns the stop reason."""
    day = facts.now.date().isoformat()
    resumed = facts.latch is not None and facts.latch.started_at is not None
    latch = mark_started(facts.latch, day=day, now=facts.now, reason=reason)
    emit(
        "fallback_ring_start",
        reason,
        reason=reason,
        resumed=resumed,
        alarm=facts.alarm_at.isoformat(),
        started_at=latch.started_at,
    )
    stopped = TERMINATED
    try:
        # Inside the try: a WAV that cannot be generated must still close
        # the latch (as "terminated"), never leave it open.
        rise, loop = ensure_pair(SYSTEM_WAV_DIR, USER_WAV_DIR)
        stopped = ring(lambda: _poll(day), rise=rise, loop=loop)
    finally:
        _close(latch, stopped)
    return stopped


def tick(now: datetime) -> Decision:
    """One timer tick: observe, log a changed decision, ring if due."""
    seen = observe(now)
    record(seen)
    facts, day = seen.facts, now.date().isoformat()
    decision = decide(facts)
    emit_on_change(
        "fallback_tick",
        f"{day}|{decision.ring}|{decision.reason}",
        f"{'ring' if decision.ring else 'quiet'}: {decision.reason}",
        ring=decision.ring,
        reason=decision.reason,
        alarm=facts.alarm_at.isoformat(),
        reachable=seen.reachable,
    )
    remember_final(day, decision.reason)
    latch = facts.latch
    if decision.ring:
        ring_now(facts, decision.reason)
    elif latch is not None and latch.started_at and not latch.stopped_at:
        _close(latch, decision.reason)
    return decision


def describe(seen: Observation, decision: Decision) -> str:
    """The ``--dry-run`` report."""
    facts = seen.facts
    verdict = "WOULD RING" if decision.ring else "quiet"
    return (
        f"{facts.now:%Y-%m-%d %H:%M} — {verdict}: {decision.reason}\n"
        f"  alarm A={facts.alarm_at:%H:%M} free_day={facts.free_day} "
        f"firebase={'ok' if seen.reachable else 'UNREACHABLE'}\n"
        f"  escaped={facts.escaped} session_started={facts.session_started} "
        f"ring_started={facts.ring_started} settled={facts.settled}\n"
        f"  latch={facts.latch}\n"
    )


def show(now: datetime) -> str:
    """The ``--show`` report: local state only, no network."""
    day = now.date().isoformat()
    alarm_at = alarm_instant(get_alarm(), now.date())
    return (
        f"today {day}: A={alarm_at:%H:%M} "
        f"free_day={freedays.is_free_day(now.date())}\n"
        f"  latch={read_latch(day)}\n"
        f"  last fallback_tick={last_value('fallback_tick')}\n"
        f"  settled={settled_reason(day, read_latch(day))}\n"
    )


def _terminate(signum: int, _frame: FrameType | None) -> None:
    """SIGTERM -> SystemExit, so ``finally`` silences the speakers."""
    raise SystemExit(128 + signum)


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    parser = mode_parser("PC fallback alarm tick", "tick", "decide and act")
    args, now = parse_with_now(parser, argv, _now)
    if args.show:
        sys.stdout.write(show(now))
    elif args.dry_run:
        seen = observe(now)
        sys.stdout.write(describe(seen, decide(seen.facts)))
    else:
        configure_logging(component="fallback")
        signal.signal(signal.SIGTERM, _terminate)
        tick(now)
    return 0


if __name__ == "__main__":
    sys.exit(main())
