"""Tests for the PC-side clamp — a synced alarm may never land later."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import pytest

from wake_alarm._constants import FALLBACK_ALARM_HOUR
from wake_alarm._sync import Alarm
from wake_alarm._trigger import (
    _clamp_to_baseline,
)


def _at(hour: int, minute: int) -> datetime:
    """Return a Sunday at the given local wall-clock time, timezone-aware.

    Built the same way production does — naive wall clock, then astimezone()
    to attach the system offset — so the tests exercise the real comparison
    semantics rather than a hand-picked fixed offset.
    """
    return datetime(2026, 7, 19, hour, minute, tzinfo=None).astimezone()


@pytest.fixture(autouse=True)
def _ungated() -> None:
    """Open every gate unless a test closes one.

    The once-per-day latch is stubbed: unstubbed it reads the *real*
    session record on the host, so a test run started while an alarm was
    actually ringing would silently invert half these assertions.
    """
    with (
        patch("wake_alarm._trigger.was_trigger_fired_today", return_value=False),
    ):
        yield


class TestClampToBaseline:
    """The PC-side watchdog: a synced alarm may never land later than 08:00."""

    def test_an_earlier_alarm_passes_through_untouched(self) -> None:
        """The phone ratchets earlier, so earlier values are legitimate."""
        alarm = Alarm(6, 30, "remote")
        assert _clamp_to_baseline(alarm) == alarm

    def test_the_baseline_itself_passes_through(self) -> None:
        """Equal to the baseline is not later than it."""
        alarm = Alarm(FALLBACK_ALARM_HOUR, 0, "remote")
        assert _clamp_to_baseline(alarm) == alarm

    def test_a_later_alarm_is_clamped_to_the_baseline(self) -> None:
        """The one direction the design forbids must not be reachable."""
        clamped = _clamp_to_baseline(Alarm(13, 0, "remote"))
        assert (clamped.hour, clamped.minute) == (FALLBACK_ALARM_HOUR, 0)
        assert clamped.source == "clamped-remote"

    def test_a_later_minute_within_the_baseline_hour_is_clamped(self) -> None:
        """08:30 is later than 08:00, so the minute matters too."""
        clamped = _clamp_to_baseline(Alarm(FALLBACK_ALARM_HOUR, 30, "cache"))
        assert (clamped.hour, clamped.minute) == (FALLBACK_ALARM_HOUR, 0)
        assert clamped.source == "clamped-cache"
