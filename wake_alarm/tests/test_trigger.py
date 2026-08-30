"""Tests for _trigger.py — the per-minute check-and-fire tick."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from wake_alarm._sync import Alarm
from wake_alarm._trigger import (
    _decide,
    _fire_window,
    _now,
    _skip_reason,
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


class TestNow:
    """Tests for the _now seam."""

    def test_returns_aware_local_time(self) -> None:
        """The clock is timezone-aware and in local time, not UTC."""
        now = _now()
        assert now.tzinfo is not None
        # Local, not UTC: the wall-clock hour must match the system clock's.
        assert now.hour == datetime.now(tz=UTC).astimezone().hour


class TestFireWindow:
    """Tests for _fire_window."""

    def test_window_starts_at_the_alarm_minute(self) -> None:
        """The fire instant is today at the alarm's H:M, seconds zeroed."""
        fire_at, _ = _fire_window(Alarm(6, 45, "remote"), _at(3, 12))
        assert fire_at == _at(6, 45)
        assert fire_at.second == 0

    def test_window_is_the_catchup_length(self) -> None:
        """The window ends TRIGGER_CATCHUP_MINUTES after the alarm."""
        fire_at, end = _fire_window(Alarm(6, 45, "remote"), _at(3, 12))
        assert (end - fire_at).total_seconds() == 60 * 60

    def test_fire_instant_is_aware(self) -> None:
        """The fire instant keeps a timezone, so comparisons are unambiguous."""
        fire_at, end = _fire_window(Alarm(6, 45, "remote"), _at(3, 12))
        assert fire_at.tzinfo is not None
        assert end.tzinfo is not None

    def test_offset_is_derived_from_the_target_wall_time(self) -> None:
        """The offset is re-derived, not inherited from *now*.

        Guards the DST case: deciding a morning alarm from a tick taken on the
        other side of a clock change must not carry *now*'s stale UTC offset.
        """
        fire_at, _ = _fire_window(Alarm(6, 45, "remote"), _at(3, 12))
        expected = datetime(2026, 7, 19, 6, 45, tzinfo=None).astimezone()
        assert fire_at.utcoffset() == expected.utcoffset()
        assert fire_at == expected


class TestSkipReason:
    """Tests for the clock-independent gates."""

    def test_open_when_nothing_blocks(self) -> None:
        """With every gate open there is no reason to skip."""
        assert _skip_reason(_at(7, 0)) is None

    def test_not_an_alarm_day(self) -> None:
        """A weekday outside ALARM_DAYS blocks firing."""
        with patch("wake_alarm._trigger.ALARM_DAYS", frozenset()):
            assert _skip_reason(_at(7, 0)) == "not an alarm day"

    def test_already_fired_today(self) -> None:
        """The once-per-day latch blocks every later tick in the window."""
        with patch(
            "wake_alarm._trigger.was_trigger_fired_today",
            return_value=True,
        ):
            assert _skip_reason(_at(7, 0)) == "already fired today"


class TestDecide:
    """Tests for the fire/don't-fire decision."""

    def test_before_the_alarm(self) -> None:
        """A tick before the alarm minute does not fire."""
        fire, reason = _decide(_at(6, 44), Alarm(6, 45, "remote"))
        assert not fire
        assert "still ahead" in reason

    def test_exactly_on_the_alarm_minute(self) -> None:
        """The alarm minute itself fires."""
        fire, _ = _decide(_at(6, 45), Alarm(6, 45, "remote"))
        assert fire

    def test_within_the_catchup_window(self) -> None:
        """A tick inside the catch-up window still fires (e.g. after resume)."""
        fire, _ = _decide(_at(7, 30), Alarm(6, 45, "remote"))
        assert fire

    def test_at_the_window_edge(self) -> None:
        """The window is half-open: its end instant no longer fires."""
        fire, reason = _decide(_at(7, 45), Alarm(6, 45, "remote"))
        assert not fire
        assert "window closed" in reason

    def test_long_after_the_alarm(self) -> None:
        """Hours later, the window is closed."""
        fire, reason = _decide(_at(20, 0), Alarm(6, 45, "remote"))
        assert not fire
        assert "window closed" in reason

    def test_gate_beats_the_clock(self) -> None:
        """A closed gate wins even at the exact alarm minute."""
        with patch(
            "wake_alarm._trigger.was_trigger_fired_today",
            return_value=True,
        ):
            fire, reason = _decide(_at(6, 45), Alarm(6, 45, "remote"))
        assert not fire
        assert reason == "already fired today"

    def test_alarm_moved_earlier_fires_immediately(self) -> None:
        """A phone alarm moved back before now fires on the very next tick."""
        fire, _ = _decide(_at(6, 50), Alarm(6, 40, "remote"))
        assert fire
