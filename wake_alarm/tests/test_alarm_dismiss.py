"""Tests for the dismiss-challenge rounds."""

from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

if TYPE_CHECKING:
    from collections.abc import Generator

from wake_alarm._alarm import (
    WakeAlarm,
)

# ---------------------------------------------------------------------------
# Helpers (duplicated from part 1 so this file is self-contained)
# ---------------------------------------------------------------------------


# Helpers (duplicated from part 1 so this file is self-contained)
# ---------------------------------------------------------------------------


def _make_mock_tk() -> MagicMock:
    """Build a MagicMock that stands in for the tkinter module."""
    mock = MagicMock()
    mock_root = MagicMock()
    mock_root.winfo_screenwidth.return_value = 1920
    mock_root.winfo_screenheight.return_value = 1080
    mock.Tk.return_value = mock_root
    # Distinct frames and buttons per call: a shared return_value would make
    # "every monitor got one" indistinguishable from "one monitor got two".
    mock.Frame.side_effect = lambda *_args, **_kwargs: MagicMock()
    mock.Button.side_effect = lambda *_args, **_kwargs: MagicMock()
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


@pytest.fixture(autouse=True)
def _block_extra_devices() -> Generator[MagicMock]:
    """Prevent real subprocess.Popen calls for extra ALSA devices."""
    with (
        patch("wake_alarm._beep_loop._play_on_all_sinks") as mock,
        patch("wake_alarm._startup._set_max_brightness"),
        patch("wake_alarm._startup._wake_display"),
        patch("wake_alarm._alarm._restore_display"),
        patch("wake_alarm._startup._warn_if_no_real_sink"),
        patch("wake_alarm._alarm._activate_all_outputs", return_value=None),
        patch("wake_alarm._alarm._restore_audio_state"),
        patch("wake_alarm._startup.turn_on_plug"),
        patch("wake_alarm._alarm.turn_off_plug"),
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


class TestWakeAlarmDismiss:
    """Tests for alarm dismiss logic."""

    def test_correct_code_dismisses_after_all_rounds(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """Entering the correct answer for every required round dismisses the alarm."""
        from wake_alarm._constants import DISMISS_ROUNDS_REQUIRED

        alarm = WakeAlarm(demo_mode=True)

        with patch(
            "wake_alarm._alarm.save_wake_state",
        ) as mock_save:
            for _ in range(DISMISS_ROUNDS_REQUIRED):
                alarm._view.entry_var.get.return_value = (
                    alarm._progress.current_challenge.answer
                )
                alarm._on_submit()

        assert alarm.dismissed is True
        mock_save.assert_called_once()
        assert mock_save.call_args[1]["skip_workout"] is True
        alarm._stop_beep.set()

    def test_first_round_correct_does_not_dismiss(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """A single correct entry is not enough — DISMISS_ROUNDS_REQUIRED is 2+."""
        alarm = WakeAlarm(demo_mode=True)
        alarm._view.entry_var.get.return_value = (
            alarm._progress.current_challenge.answer
        )

        alarm._on_submit()

        assert alarm.dismissed is False
        assert alarm._progress.rounds_completed == 1
        alarm._stop_beep.set()

    def test_first_round_correct_non_flash_next_no_countdown(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """When next challenge is math, no flash countdown is started."""
        from wake_alarm._challenges import _Challenge

        alarm = WakeAlarm(demo_mode=True)
        alarm._view.entry_var.get.return_value = (
            alarm._progress.current_challenge.answer
        )
        next_math = _Challenge(kind="math", display="2 + 2 = ?", answer="4", hint="x")
        with patch("wake_alarm._alarm._make_challenge", return_value=next_math):
            alarm._on_submit()

        assert alarm._progress.current_challenge.kind == "math"
        assert alarm.dismissed is False
        alarm._stop_beep.set()

    def test_wrong_code_does_not_dismiss(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """Entering the wrong answer shows an error without dismissing."""
        from wake_alarm._challenges import _Challenge

        alarm = WakeAlarm(demo_mode=True)
        # Use a pinned math challenge so the non-flash wrong-answer branch is covered.
        alarm._progress.current_challenge = _Challenge(
            kind="math", display="2 + 2 = ?", answer="4", hint="test"
        )
        alarm._view.entry_var.get.return_value = "99"

        alarm._on_submit()

        assert alarm.dismissed is False
        alarm._stop_beep.set()

    def test_skip_window_expired_keeps_alarm_running(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """Skip-window expiry denies the skip but does NOT stop the alarm."""
        del mock_tk_module
        alarm = WakeAlarm(demo_mode=True)

        with patch(
            "wake_alarm._alarm.save_wake_state",
        ) as mock_save:
            alarm._on_skip_window_expired()

        # Alarm stays active and audible; only the skip reward is gone.
        assert alarm._progress.skip_earnable is False
        assert alarm._active is True
        assert alarm.dismissed is False
        assert not alarm._stop_beep.is_set()
        mock_save.assert_not_called()
        alarm._view._views[0].labels.info.configure.assert_called()
        alarm._stop_beep.set()

    def test_skip_window_expired_noop_if_not_active(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """Expiry is a no-op if alarm is no longer active."""
        del mock_tk_module
        alarm = WakeAlarm(demo_mode=True)
        alarm._active = False

        alarm._on_skip_window_expired()

        # skip_earnable stays at its initial True (method returned early).
        assert alarm._progress.skip_earnable is True
        alarm._stop_beep.set()

    def test_dismiss_after_skip_window_earns_no_skip(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """Typing all rounds after the skip window stops the alarm without a skip."""
        from wake_alarm._constants import DISMISS_ROUNDS_REQUIRED

        alarm = WakeAlarm(demo_mode=True)
        alarm._progress.skip_earnable = False

        with patch(
            "wake_alarm._alarm.save_wake_state",
        ) as mock_save:
            for _ in range(DISMISS_ROUNDS_REQUIRED):
                alarm._view.entry_var.get.return_value = (
                    alarm._progress.current_challenge.answer
                )
                alarm._on_submit()

        assert alarm.dismissed is True
        assert mock_save.call_args[1]["skip_workout"] is False
        alarm._stop_beep.set()
