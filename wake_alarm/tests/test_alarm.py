"""Tests for _alarm.py — wake alarm daemon, UI, and beep logic."""

from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

if TYPE_CHECKING:
    from collections.abc import Generator

from wake_alarm._audio import (
    _beep_loud,
    _beep_medium,
    _beep_soft,
    _speaker_test_path,
)
from wake_alarm._challenges import (
    _DISMISS_CHARS,
    _generate_code,
)
from wake_alarm._constants import (
    DISMISS_CODE_LENGTH,
)
from wake_alarm._gating import (
    is_alarm_day as _is_alarm_day,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_tk() -> MagicMock:
    """Build a MagicMock that stands in for the tkinter module."""
    mock = MagicMock()
    mock_root = MagicMock()
    mock_root.winfo_screenwidth.return_value = 1920
    mock_root.winfo_screenheight.return_value = 1080
    mock.Tk.return_value = mock_root
    mock.Frame.return_value = MagicMock()
    mock.Label.return_value = MagicMock()
    mock.Entry.return_value = MagicMock()
    mock.TclError = tk.TclError
    mock.END = tk.END
    return mock


@pytest.fixture(autouse=True)
def _block_real_tk() -> Generator[MagicMock]:
    """Prevent any real Tk windows in tests."""
    mock = _make_mock_tk()
    with (
        patch("wake_alarm._alarm.tk", mock),
        patch("wake_alarm._dismiss_view.tk", mock),
        patch("wake_alarm._alarm_view.tk", mock),
        patch(
            "wake_alarm._alarm.GateRoot",
            return_value=mock.Tk.return_value,
        ),
    ):
        yield mock


@pytest.fixture
def mock_tk_module() -> Generator[MagicMock]:
    """Provide explicit access to the mocked tk module."""
    mock = _make_mock_tk()
    with (
        patch("wake_alarm._alarm.tk", mock),
        patch("wake_alarm._dismiss_view.tk", mock),
        patch("wake_alarm._alarm_view.tk", mock),
        patch(
            "wake_alarm._alarm.GateRoot",
            return_value=mock.Tk.return_value,
        ),
    ):
        yield mock


# ---------------------------------------------------------------------------
# Unit tests for pure functions
# ---------------------------------------------------------------------------


class TestGenerateCode:
    """Tests for _generate_code."""

    def test_correct_length(self) -> None:
        """Generated code has the configured length."""
        code = _generate_code()
        assert len(code) == DISMISS_CODE_LENGTH

    def test_all_alphanumeric(self) -> None:
        """Generated code uses only the unambiguous alphanumeric charset."""

        code = _generate_code()
        assert all(c in _DISMISS_CHARS for c in code)

    def test_different_codes(self) -> None:
        """Two calls produce different codes (probabilistic, but safe)."""
        codes = {_generate_code() for _ in range(50)}
        assert len(codes) > 1


class TestIsAlarmDay:
    """Tests for _is_alarm_day."""

    def test_monday_is_alarm_day(self) -> None:
        """Monday (weekday=0) is an alarm day."""
        from datetime import datetime

        # Create a date that is Monday
        with patch(
            "wake_alarm._alarm.datetime",
        ) as mock_dt:
            mock_now = MagicMock()
            mock_now.weekday.return_value = 0  # Monday
            mock_dt.now.return_value = mock_now
            mock_dt.side_effect = datetime
            assert _is_alarm_day() is True

    def test_tuesday_is_alarm_day(self) -> None:
        """Tuesday (weekday=1) is an alarm day."""
        with patch(
            "wake_alarm._alarm.datetime",
        ) as mock_dt:
            mock_now = MagicMock()
            mock_now.weekday.return_value = 1  # Tuesday
            mock_dt.now.return_value = mock_now
            assert _is_alarm_day() is True

    def test_friday_is_alarm_day(self) -> None:
        """Friday (weekday=4) is an alarm day."""
        with patch(
            "wake_alarm._alarm.datetime",
        ) as mock_dt:
            mock_now = MagicMock()
            mock_now.weekday.return_value = 4  # Friday
            mock_dt.now.return_value = mock_now
            assert _is_alarm_day() is True

    def test_saturday_is_alarm_day(self) -> None:
        """Saturday (weekday=5) is an alarm day."""
        with patch(
            "wake_alarm._alarm.datetime",
        ) as mock_dt:
            mock_now = MagicMock()
            mock_now.weekday.return_value = 5
            mock_dt.now.return_value = mock_now
            assert _is_alarm_day() is True

    def test_sunday_is_alarm_day(self) -> None:
        """Sunday (weekday=6) is an alarm day."""
        with patch(
            "wake_alarm._alarm.datetime",
        ) as mock_dt:
            mock_now = MagicMock()
            mock_now.weekday.return_value = 6
            mock_dt.now.return_value = mock_now
            assert _is_alarm_day() is True

    def test_wednesday_is_alarm_day(self) -> None:
        """Wednesday (weekday=2) is an alarm day."""
        with patch(
            "wake_alarm._alarm.datetime",
        ) as mock_dt:
            mock_now = MagicMock()
            mock_now.weekday.return_value = 2
            mock_dt.now.return_value = mock_now
            assert _is_alarm_day() is True

    def test_thursday_is_alarm_day(self) -> None:
        """Thursday (weekday=3) is an alarm day."""
        with patch(
            "wake_alarm._alarm.datetime",
        ) as mock_dt:
            mock_now = MagicMock()
            mock_now.weekday.return_value = 3
            mock_dt.now.return_value = mock_now
            assert _is_alarm_day() is True


class TestSpeakerTestPath:
    """Tests for _speaker_test_path."""

    def test_returns_path_when_found(self) -> None:
        """Return full path when speaker-test is available."""
        with patch(
            "wake_alarm._audio.shutil.which",
            return_value="/usr/bin/speaker-test",
        ):
            assert _speaker_test_path() == "/usr/bin/speaker-test"

    def test_raises_when_not_found(self) -> None:
        """Raise FileNotFoundError when speaker-test is missing."""
        with (
            patch(
                "wake_alarm._audio.shutil.which",
                return_value=None,
            ),
            pytest.raises(FileNotFoundError, match="speaker-test not found"),
        ):
            _speaker_test_path()


class TestBeepFunctions:
    """Tests for beep helper functions."""

    def test_beep_soft_writes_bell(self) -> None:
        """_beep_soft writes terminal bell character."""
        with patch("wake_alarm._audio.sys") as mock_sys:
            mock_sys.stdout = MagicMock()
            _beep_soft()
            mock_sys.stdout.write.assert_called_once_with("\a")
            mock_sys.stdout.flush.assert_called_once()

    def test_beep_medium_delegates_to_play_tone(self) -> None:
        """_beep_medium just delegates to _play_tone."""
        with patch("wake_alarm._audio._play_tone") as mock_play:
            _beep_medium(frequency=800)
            mock_play.assert_called_once_with(800)

    def test_beep_loud_delegates_to_play_tone(self) -> None:
        """_beep_loud just delegates to _play_tone."""
        with patch("wake_alarm._audio._play_tone") as mock_play:
            _beep_loud(frequency=1200)
            mock_play.assert_called_once_with(1200)
