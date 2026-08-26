"""The background thread that sounds the alarm.

Split out of ``_alarm.py`` so the loop can be exercised without a Tk window,
and so the escalation decision itself stays in ``_escalation`` as a pure
function.

The loop plays on **every** real sink each cycle rather than choosing one
output: a speaker that is switched off cannot be revived by software, so the
answer is to drive every other output in parallel.
"""

from __future__ import annotations

from collections.abc import Callable
import logging
import threading
import time

from wake_alarm._audio import (
    _beep_loud,
    _beep_medium,
    _beep_soft,
    _play_on_all_sinks,
)
from wake_alarm._escalation import BeepPlan, plan_for

_Monotonic = Callable[[], float]

_logger = logging.getLogger(__name__)


def _sound(plan: BeepPlan) -> None:
    """Emit one cycle of audio for *plan*.

    Args:
        plan: The decision for this iteration.
    """
    if plan.frequency is None:
        return
    _play_on_all_sinks(plan.frequency)
    if plan.phase == "soft":
        _beep_soft()
    elif plan.phase == "medium":
        _beep_medium()
    else:
        _beep_loud(plan.frequency)


def run_beep_loop(
    stop: threading.Event,
    started_at: float,
    *,
    monotonic: _Monotonic = time.monotonic,
) -> None:
    """Sound the alarm until *stop* is set.

    Args:
        stop: Set on dismissal (and by the caller's exit paths).
        started_at: Monotonic timestamp when the ring began.
        monotonic: Clock source, injected for tests.

    The failsafe is measured from this side's own monotonic clock, never from
    a timestamp compared across devices: a skewed phone clock must not be able
    to silence the PC early, nor keep it sounding forever.
    """
    announced_silence = False
    while not stop.is_set():
        elapsed = monotonic() - started_at
        plan = plan_for(elapsed)
        if plan.silenced and not announced_silence:
            announced_silence = True
            _logger.warning(
                "Failsafe reached after %.0fs: audio stops, but the lock and "
                "challenge remain until dismissed.",
                elapsed,
                extra={"event": "failsafe_silence", "elapsed_s": round(elapsed)},
            )
        _sound(plan)
        stop.wait(plan.interval)


def start_beep_thread(stop: threading.Event, started_at: float) -> threading.Thread:
    """Run :func:`run_beep_loop` on a daemon thread.

    Args:
        stop: Set on dismissal.
        started_at: Monotonic timestamp when the ring began.

    Returns:
        The started thread.
    """
    thread = threading.Thread(
        target=run_beep_loop,
        args=(stop, started_at),
        daemon=True,
        name="wake-alarm-beep",
    )
    thread.start()
    return thread
