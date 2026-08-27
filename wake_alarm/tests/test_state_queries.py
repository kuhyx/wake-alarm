"""Tests for _state.py's read-side queries — the workout skip, and the two
'already done today' gates the trigger consults.

Split out of test_state.py for the 250-line gate; that file keeps the
UTC day key and the save/load round-trip."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from wake_alarm._state import (
    _today_str,
    has_workout_skip_today,
    was_alarm_dismissed_today,
    was_workout_logged_today,
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def wake_state_file(tmp_path: Path) -> Path:
    """Provide a temporary wake state file path."""
    return tmp_path / "wake_state.json"


@pytest.fixture(autouse=True)
def _patch_wake_state_file(wake_state_file: Path) -> None:
    """Redirect WAKE_STATE_FILE to tmp_path for all tests."""
    with patch(
        "wake_alarm._state.WAKE_STATE_FILE",
        wake_state_file,
    ):
        yield



class TestHasWorkoutSkipToday:
    """Tests for has_workout_skip_today."""

    def test_returns_false_when_no_state(self) -> None:
        """Return False when no state file exists."""
        assert has_workout_skip_today() is False

    def test_returns_true_when_skip_granted(
        self,
        wake_state_file: Path,
    ) -> None:
        """Return True when today's state has skip_workout=True."""
        state = {
            "date": _today_str(),
            "skip_workout": True,
            "dismissed_at": "07:04",
            "hmac": "sig",
        }
        wake_state_file.write_text(json.dumps(state))
        with patch(
            "wake_alarm._state.verify_entry_hmac",
            return_value=True,
        ):
            assert has_workout_skip_today() is True

    def test_returns_false_when_skip_not_granted(
        self,
        wake_state_file: Path,
    ) -> None:
        """Return False when today's state has skip_workout=False."""
        state = {
            "date": _today_str(),
            "skip_workout": False,
            "dismissed_at": None,
            "hmac": "sig",
        }
        wake_state_file.write_text(json.dumps(state))
        with patch(
            "wake_alarm._state.verify_entry_hmac",
            return_value=True,
        ):
            assert has_workout_skip_today() is False


class TestWasAlarmDismissedToday:
    """Tests for was_alarm_dismissed_today."""

    def test_returns_false_when_no_state(self) -> None:
        """Return False when no state file exists."""
        assert was_alarm_dismissed_today() is False

    def test_returns_true_when_dismissed(
        self,
        wake_state_file: Path,
    ) -> None:
        """Return True when alarm was dismissed today."""
        state = {
            "date": _today_str(),
            "dismissed_at": "07:04",
            "skip_workout": True,
            "hmac": "sig",
        }
        wake_state_file.write_text(json.dumps(state))
        with patch(
            "wake_alarm._state.verify_entry_hmac",
            return_value=True,
        ):
            assert was_alarm_dismissed_today() is True

    def test_returns_false_when_not_dismissed(
        self,
        wake_state_file: Path,
    ) -> None:
        """Return False when alarm was not dismissed."""
        state = {
            "date": _today_str(),
            "dismissed_at": None,
            "skip_workout": False,
            "hmac": "sig",
        }
        wake_state_file.write_text(json.dumps(state))
        with patch(
            "wake_alarm._state.verify_entry_hmac",
            return_value=True,
        ):
            assert was_alarm_dismissed_today() is False


class TestWasWorkoutLoggedToday:
    """Tests for was_workout_logged_today."""

    def test_returns_false_when_file_missing(self, tmp_path: Path) -> None:
        """Return False when the workout log file does not exist."""
        with patch(
            "wake_alarm._state.WORKOUT_LOG_FILE",
            tmp_path / "workout_log.json",
        ):
            assert was_workout_logged_today() is False

    def test_returns_false_when_file_is_invalid_json(self, tmp_path: Path) -> None:
        """Return False when the workout log contains invalid JSON."""
        log_file = tmp_path / "workout_log.json"
        log_file.write_text("not json {{{")
        with patch(
            "wake_alarm._state.WORKOUT_LOG_FILE",
            log_file,
        ):
            assert was_workout_logged_today() is False

    def test_returns_false_when_file_is_not_a_dict(self, tmp_path: Path) -> None:
        """Return False when the workout log is not a JSON object."""
        log_file = tmp_path / "workout_log.json"
        log_file.write_text(json.dumps([1, 2, 3]))
        with patch(
            "wake_alarm._state.WORKOUT_LOG_FILE",
            log_file,
        ):
            assert was_workout_logged_today() is False

    def test_returns_false_when_today_absent(self, tmp_path: Path) -> None:
        """Return False when the workout log has no entry for today."""
        log_file = tmp_path / "workout_log.json"
        log_file.write_text(json.dumps({"1999-01-01": {"type": "old"}}))
        with patch(
            "wake_alarm._state.WORKOUT_LOG_FILE",
            log_file,
        ):
            assert was_workout_logged_today() is False

    def test_returns_true_when_today_present(self, tmp_path: Path) -> None:
        """Return True when today's date key exists in the workout log."""
        log_file = tmp_path / "workout_log.json"
        log_file.write_text(json.dumps({_today_str(): {"type": "phone_verified"}}))
        with patch(
            "wake_alarm._state.WORKOUT_LOG_FILE",
            log_file,
        ):
            assert was_workout_logged_today() is True
