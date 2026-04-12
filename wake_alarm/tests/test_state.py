"""Tests for _state.py — HMAC-signed wake state management."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from python_pkg.wake_alarm._state import (
    _today_str,
    has_workout_skip_today,
    load_wake_state,
    save_wake_state,
    was_alarm_dismissed_today,
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
        "python_pkg.wake_alarm._state.WAKE_STATE_FILE",
        wake_state_file,
    ):
        yield


class TestTodayStr:
    """Tests for _today_str helper."""

    def test_returns_date_string(self) -> None:
        """Return a YYYY-MM-DD string for today."""
        result = _today_str()
        assert len(result) == 10
        assert result[4] == "-"
        assert result[7] == "-"


class TestSaveWakeState:
    """Tests for save_wake_state."""

    def test_saves_with_hmac(self, wake_state_file: Path) -> None:
        """Save state with HMAC signature when key is available."""
        with patch(
            "python_pkg.wake_alarm._state.compute_entry_hmac",
            return_value="fakesig",
        ):
            result = save_wake_state(
                dismissed_at="2026-04-12T07:04:00+00:00",
                skip_workout=True,
            )

        assert result is True
        data = json.loads(wake_state_file.read_text())
        assert data["skip_workout"] is True
        assert data["dismissed_at"] == "2026-04-12T07:04:00+00:00"
        assert data["hmac"] == "fakesig"
        assert data["date"] == _today_str()

    def test_saves_without_hmac(self, wake_state_file: Path) -> None:
        """Save unsigned state when HMAC key is unavailable."""
        with patch(
            "python_pkg.wake_alarm._state.compute_entry_hmac",
            return_value=None,
        ):
            result = save_wake_state(
                dismissed_at=None,
                skip_workout=False,
            )

        assert result is True
        data = json.loads(wake_state_file.read_text())
        assert data["skip_workout"] is False
        assert "hmac" not in data

    def test_returns_false_on_write_error(self, wake_state_file: Path) -> None:
        """Return False when file cannot be written."""
        with (
            patch(
                "python_pkg.wake_alarm._state.compute_entry_hmac",
                return_value="sig",
            ),
            patch(
                "python_pkg.wake_alarm._state.WAKE_STATE_FILE",
                wake_state_file / "nonexistent_dir" / "file.json",
            ),
        ):
            result = save_wake_state(dismissed_at=None, skip_workout=False)

        assert result is False


class TestLoadWakeState:
    """Tests for load_wake_state."""

    def test_returns_none_when_file_missing(self) -> None:
        """Return None when state file doesn't exist."""
        assert load_wake_state() is None

    def test_returns_none_for_wrong_date(
        self,
        wake_state_file: Path,
    ) -> None:
        """Return None when state is from a different day."""
        state = {"date": "1999-01-01", "skip_workout": True, "hmac": "x"}
        wake_state_file.write_text(json.dumps(state))
        assert load_wake_state() is None

    def test_returns_none_for_invalid_json(
        self,
        wake_state_file: Path,
    ) -> None:
        """Return None when file contains invalid JSON."""
        wake_state_file.write_text("not json {{{")
        assert load_wake_state() is None

    def test_returns_none_for_non_dict(
        self,
        wake_state_file: Path,
    ) -> None:
        """Return None when file contains a non-dict JSON value."""
        wake_state_file.write_text(json.dumps([1, 2, 3]))
        assert load_wake_state() is None

    def test_returns_none_for_bad_hmac(
        self,
        wake_state_file: Path,
    ) -> None:
        """Return None when HMAC verification fails."""
        state = {
            "date": _today_str(),
            "skip_workout": True,
            "dismissed_at": "07:00",
            "hmac": "badsig",
        }
        wake_state_file.write_text(json.dumps(state))
        with patch(
            "python_pkg.wake_alarm._state.verify_entry_hmac",
            return_value=False,
        ):
            assert load_wake_state() is None

    def test_returns_state_for_valid_today(
        self,
        wake_state_file: Path,
    ) -> None:
        """Return state dict when file is valid and for today."""
        state = {
            "date": _today_str(),
            "skip_workout": True,
            "dismissed_at": "07:04",
            "hmac": "validsig",
        }
        wake_state_file.write_text(json.dumps(state))
        with patch(
            "python_pkg.wake_alarm._state.verify_entry_hmac",
            return_value=True,
        ):
            result = load_wake_state()

        assert result is not None
        assert result["skip_workout"] is True


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
            "python_pkg.wake_alarm._state.verify_entry_hmac",
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
            "python_pkg.wake_alarm._state.verify_entry_hmac",
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
            "python_pkg.wake_alarm._state.verify_entry_hmac",
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
            "python_pkg.wake_alarm._state.verify_entry_hmac",
            return_value=True,
        ):
            assert was_alarm_dismissed_today() is False
