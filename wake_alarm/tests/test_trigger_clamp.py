"""Tests for the PC-side clamp — a synced alarm may never land later."""

from __future__ import annotations

from datetime import date, datetime
import logging
from unittest.mock import patch

import pytest

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


# 2026-09-26 is the ramp's first step: 07:59.
_DAY = date(2026, 9, 26)


class TestClampToBaseline:
    """The PC-side watchdog: a synced alarm may never land later than the ramp."""

    def test_an_earlier_alarm_passes_through_untouched(self) -> None:
        """The phone ratchets earlier, so earlier values are legitimate."""
        alarm = Alarm(6, 30, "remote")
        assert _clamp_to_baseline(alarm, _DAY) == alarm

    def test_the_baseline_itself_passes_through(self) -> None:
        """Equal to the day's baseline is not later than it."""
        alarm = Alarm(7, 59, "remote")
        assert _clamp_to_baseline(alarm, _DAY) == alarm

    def test_a_later_alarm_is_clamped_to_the_baseline(self) -> None:
        """The one direction the design forbids must not be reachable."""
        clamped = _clamp_to_baseline(Alarm(13, 0, "remote"), _DAY)
        assert (clamped.hour, clamped.minute) == (7, 59)
        assert clamped.source == "clamped-remote"

    def test_before_the_ramp_the_baseline_is_eight(self) -> None:
        """08:30 is later than 08:00, so the minute matters too."""
        clamped = _clamp_to_baseline(Alarm(8, 30, "cache"), date(2026, 9, 1))
        assert (clamped.hour, clamped.minute) == (8, 0)
        assert clamped.source == "clamped-cache"

    def test_yesterdays_time_is_clamped_quietly(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A record a minute behind the ramp is lag, not tampering: INFO only.

        This runs every tick, so a WARNING here would be 1440 lines a day on
        every morning the phone app was not opened.
        """
        with caplog.at_level(logging.INFO, logger="wake_alarm._trigger"):
            clamped = _clamp_to_baseline(Alarm(8, 0, "remote"), _DAY)
        assert (clamped.hour, clamped.minute) == (7, 59)
        assert [r.levelno for r in caplog.records] == [logging.INFO]

    def test_later_than_eight_still_warns(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Past the old 08:00 baseline no phone could have published it."""
        with caplog.at_level(logging.INFO, logger="wake_alarm._trigger"):
            _clamp_to_baseline(Alarm(8, 1, "remote"), _DAY)
        assert [r.levelno for r in caplog.records] == [logging.WARNING]
