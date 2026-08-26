"""Tests for the day/dismissed/workout gate."""

from __future__ import annotations

from unittest.mock import patch

from wake_alarm._gating import (
    should_run_alarm as _should_run_alarm,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class TestShouldRunAlarm:
    """Tests for _should_run_alarm."""

    def test_returns_false_on_non_alarm_day(self) -> None:
        """Return False when today is not an alarm day."""
        with patch(
            "wake_alarm._gating.is_alarm_day",
            return_value=False,
        ):
            assert _should_run_alarm() is False

    def test_returns_false_when_already_dismissed(self) -> None:
        """Return False when alarm was already dismissed today."""
        with (
            patch(
                "wake_alarm._gating.is_alarm_day",
                return_value=True,
            ),
            patch(
                "wake_alarm._gating.was_alarm_dismissed_today",
                return_value=True,
            ),
        ):
            assert _should_run_alarm() is False

    def test_returns_true_when_alarm_day_and_not_dismissed(self) -> None:
        """Return True when today is alarm day and not yet dismissed."""
        with (
            patch(
                "wake_alarm._gating.is_alarm_day",
                return_value=True,
            ),
            patch(
                "wake_alarm._gating.was_alarm_dismissed_today",
                return_value=False,
            ),
            patch(
                "wake_alarm._gating.was_workout_logged_today",
                return_value=False,
            ),
        ):
            assert _should_run_alarm() is True

    def test_returns_false_when_workout_already_logged(self) -> None:
        """Return False when workout was already logged today."""
        with (
            patch(
                "wake_alarm._gating.is_alarm_day",
                return_value=True,
            ),
            patch(
                "wake_alarm._gating.was_alarm_dismissed_today",
                return_value=False,
            ),
            patch(
                "wake_alarm._gating.was_workout_logged_today",
                return_value=True,
            ),
        ):
            assert _should_run_alarm() is False
