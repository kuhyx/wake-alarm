"""Tests for the beep escalation ladder and the audio failsafe."""

from __future__ import annotations

import pytest

from wake_alarm._constants import (
    ESCAPE_OFFER_AFTER_SECONDS,
    FAILSAFE_SILENCE_SECONDS,
    PHASE_MEDIUM_END,
    PHASE_SOFT_END,
)
from wake_alarm._escalation import (
    LOUD_HIGH_FREQUENCY,
    LOUD_LOW_FREQUENCY,
    MEDIUM_FREQUENCY,
    SOFT_FREQUENCY,
    plan_for,
)


def test_starts_on_the_soft_rung() -> None:
    """The first seconds are the gentlest tone."""
    plan = plan_for(0.0)
    assert plan.frequency == SOFT_FREQUENCY
    assert plan.phase == "soft"


def test_escalates_to_medium() -> None:
    """Crossing the soft boundary raises the pitch."""
    assert plan_for(PHASE_SOFT_END * 60).frequency == MEDIUM_FREQUENCY


def test_escalates_to_loud() -> None:
    """Crossing the medium boundary reaches the loud rung."""
    assert plan_for(PHASE_MEDIUM_END * 60).phase == "loud"


def test_loud_phase_alternates_between_two_tones() -> None:
    """A changing pitch stays salient where a constant one is tuned out."""
    seen = {plan_for(PHASE_MEDIUM_END * 60 + offset).frequency for offset in range(20)}
    assert seen == {LOUD_LOW_FREQUENCY, LOUD_HIGH_FREQUENCY}


def test_intervals_shorten_as_it_escalates() -> None:
    """Each rung beeps more often than the last."""
    soft = plan_for(0.0).interval
    medium = plan_for(PHASE_SOFT_END * 60).interval
    loud = plan_for(PHASE_MEDIUM_END * 60).interval
    assert soft > medium > loud


def test_failsafe_silences_audio_at_the_threshold() -> None:
    """At the failsafe the tone stops."""
    plan = plan_for(FAILSAFE_SILENCE_SECONDS)
    assert plan.frequency is None
    assert plan.silenced is True


def test_audio_still_sounds_just_before_the_failsafe() -> None:
    """The boundary is exclusive; a moment earlier the alarm is still loud."""
    plan = plan_for(FAILSAFE_SILENCE_SECONDS - 1)
    assert plan.frequency is not None
    assert plan.silenced is False


@pytest.mark.parametrize("extra", [1, 60, 600, 3600])
def test_stays_silent_after_the_failsafe(extra: int) -> None:
    """Silence is permanent for the rest of the ring; it never resumes."""
    assert plan_for(FAILSAFE_SILENCE_SECONDS + extra).silenced is True


def test_reaches_the_loud_phase_before_the_failsafe() -> None:
    """The whole point: the alarm must get maximally annoying before it stops.

    A regression here would silently reduce the alarm to its softest tone,
    which is exactly the bug this ordering exists to prevent.
    """
    assert PHASE_MEDIUM_END * 60 < FAILSAFE_SILENCE_SECONDS


def test_spends_most_of_the_ring_on_the_loud_rung() -> None:
    """Loud should dominate the audible window, not be a brief tail."""
    loud_seconds = FAILSAFE_SILENCE_SECONDS - PHASE_MEDIUM_END * 60
    assert loud_seconds >= FAILSAFE_SILENCE_SECONDS / 2


def test_escape_hatch_does_not_open_when_the_sound_stops() -> None:
    """Offering the hatch exactly as the alarm goes quiet makes it too easy."""
    assert ESCAPE_OFFER_AFTER_SECONDS != FAILSAFE_SILENCE_SECONDS
    assert ESCAPE_OFFER_AFTER_SECONDS > FAILSAFE_SILENCE_SECONDS
