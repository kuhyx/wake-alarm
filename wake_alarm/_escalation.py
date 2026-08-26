"""Decide what the alarm should sound like at a given point in the ring.

Split out of ``_alarm.py`` so the escalation ladder -- and, more importantly,
the failsafe that silences it -- is testable without a Tk window, a lock, or a
sound card.

The failsafe silences **audio only**. The lock, the typed challenge and the
workout gate all persist: a five-minute wait must not become a way to get back
into bed. What it protects against is a runaway alarm nobody is present to
dismiss (an empty flat, a forgotten travel day), which is a neighbour problem,
not a wake-up problem.
"""

from __future__ import annotations

from dataclasses import dataclass

from wake_alarm._constants import (
    FAILSAFE_SILENCE_SECONDS,
    LOUD_TOGGLE_INTERVAL,
    MEDIUM_BEEP_INTERVAL,
    PHASE_MEDIUM_END,
    PHASE_SOFT_END,
    SOFT_BEEP_INTERVAL,
)

# Tone frequencies for each rung of the ladder.
SOFT_FREQUENCY = 440
MEDIUM_FREQUENCY = 1000
LOUD_LOW_FREQUENCY = 800
LOUD_HIGH_FREQUENCY = 1200


@dataclass(frozen=True)
class BeepPlan:
    """What the beep loop should do for one iteration.

    Attributes:
        frequency: Tone to play, or None when the failsafe has silenced audio.
        interval: Seconds to wait before reconsidering.
        phase: Name of the rung, for logging.
        silenced: True once the failsafe has stopped the sound.
    """

    frequency: int | None
    interval: float
    phase: str
    silenced: bool


def plan_for(elapsed_seconds: float) -> BeepPlan:
    """Choose the beep behaviour for a ring that started *elapsed_seconds* ago.

    Args:
        elapsed_seconds: Seconds since the alarm began sounding.

    Returns:
        The plan for this iteration.
    """
    if elapsed_seconds >= FAILSAFE_SILENCE_SECONDS:
        # Audio only. The caller keeps the lock and the challenge up.
        return BeepPlan(
            frequency=None,
            interval=LOUD_TOGGLE_INTERVAL,
            phase="failsafe-silent",
            silenced=True,
        )
    elapsed_minutes = elapsed_seconds / 60.0
    if elapsed_minutes < PHASE_SOFT_END:
        return BeepPlan(SOFT_FREQUENCY, SOFT_BEEP_INTERVAL, "soft", silenced=False)
    if elapsed_minutes < PHASE_MEDIUM_END:
        return BeepPlan(
            MEDIUM_FREQUENCY,
            MEDIUM_BEEP_INTERVAL,
            "medium",
            silenced=False,
        )
    # Alternate two tones: a changing pitch stays salient where a constant one
    # is tuned out.
    alternate = int(elapsed_minutes * 10) % 2 == 0
    frequency = LOUD_LOW_FREQUENCY if alternate else LOUD_HIGH_FREQUENCY
    return BeepPlan(frequency, LOUD_TOGGLE_INTERVAL, "loud", silenced=False)
