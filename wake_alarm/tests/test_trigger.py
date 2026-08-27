"""Tests for _trigger.py — the per-minute check-and-fire tick."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from wake_alarm import _alarm_session
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

    ``should_refire`` is stubbed here too: unstubbed it reads the *real*
    session record on the host, so a test run started while an alarm was
    actually ringing would silently invert half these assertions.
    """
    with (
        patch("wake_alarm._trigger.was_alarm_dismissed_today", return_value=False),
        patch("wake_alarm._trigger.was_workout_logged_today", return_value=False),
        patch("wake_alarm._trigger.should_refire", return_value=False),
    ):
        yield


class TestNow:
    """Tests for the _now seam."""

    def test_returns_aware_local_time(self) -> None:
        """The clock is timezone-aware and in local time, not UTC."""
        now = _now()
        assert now.tzinfo is not None
        # Local, not UTC: the wall-clock hour must match the system clock's.
        assert now.hour == datetime.now(tz=timezone.utc).astimezone().hour


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

    def test_already_dismissed(self) -> None:
        """A dismissal recorded today blocks a re-fire."""
        with patch(
            "wake_alarm._trigger.was_alarm_dismissed_today",
            return_value=True,
        ):
            assert _skip_reason(_at(7, 0)) == "alarm already dismissed today"

    def test_workout_already_logged(self) -> None:
        """A logged workout means the alarm is no longer needed."""
        with patch("wake_alarm._trigger.was_workout_logged_today", return_value=True):
            assert _skip_reason(_at(7, 0)) == "workout already logged today"


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
            "wake_alarm._trigger.was_alarm_dismissed_today",
            return_value=True,
        ):
            fire, reason = _decide(_at(6, 45), Alarm(6, 45, "remote"))
        assert not fire
        assert reason == "alarm already dismissed today"

    def test_alarm_moved_earlier_fires_immediately(self) -> None:
        """A phone alarm moved back before now fires on the very next tick."""
        fire, _ = _decide(_at(6, 50), Alarm(6, 40, "remote"))
        assert fire


class TestRefireOnAnUnfinishedSession:
    """A power-off mid-alarm must not be a way out."""

    def test_refires_long_after_the_window_closed(self) -> None:
        """The whole point: the machine may have been off for the window.

        Without this, holding the power button ends the alarm for good --
        the catch-up window closes while the PC is down and nothing on disk
        ever said an alarm was ringing.
        """
        with patch("wake_alarm._trigger.should_refire", return_value=True):
            fire, reason = _decide(_at(20, 0), Alarm(6, 45, "remote"))
        assert fire
        assert "cut short" in reason

    def test_dismissed_gate_still_beats_a_refire(self) -> None:
        """The ordinary gates are checked first and still win."""
        with (
            patch("wake_alarm._trigger.should_refire", return_value=True),
            patch(
                "wake_alarm._trigger.was_alarm_dismissed_today",
                return_value=True,
            ),
        ):
            fire, reason = _decide(_at(20, 0), Alarm(6, 45, "remote"))
        assert not fire
        assert reason == "alarm already dismissed today"

    def test_end_to_end_through_a_real_session_record(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_decide against a real record, with should_refire NOT patched.

        Every other test here stubs ``should_refire``, so the wiring between
        the record on disk and the decision was untested -- and a manual run
        found it broken while the whole suite stayed green. This is the
        deterministic version of that manual check.
        """
        monkeypatch.setattr(
            _alarm_session, "ALARM_SESSION_FILE", tmp_path / "session.json"
        )
        now = _at(20, 0)
        # The record is stamped by the alarm process, which ran at fire time --
        # not at this tick. Pin its clock to the same fictional morning as the
        # tick, or the two dates are years apart and the age check is
        # meaningless.
        monkeypatch.setattr(_alarm_session, "_now", lambda: _at(19, 30))
        alarm = Alarm(6, 45, "remote")

        with patch("wake_alarm._trigger.should_refire", _alarm_session.should_refire):
            assert _decide(now, alarm)[0] is False  # window closed, no record

            _alarm_session.start_session("wake-20260719-0645")
            fire, reason = _decide(now, alarm)
            assert fire, "a cut-short alarm must ring again"
            assert "cut short" in reason

            _alarm_session.finish_session()
            assert _decide(now, alarm)[0] is False  # dismissed stays dismissed

    def test_refire_is_asked_about_the_tick_instant(self) -> None:
        """The session's age is measured against the tick, not wall-clock now."""
        with patch("wake_alarm._trigger.should_refire") as refire:
            refire.return_value = False
            _decide(_at(20, 0), Alarm(6, 45, "remote"))
        refire.assert_called_once_with(now=_at(20, 0))
