"""Tests for _alarm.py — WakeAlarm init, dismiss, run, and beep phases (part 2)."""

from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

if TYPE_CHECKING:
    from collections.abc import Generator

from python_pkg.wake_alarm._alarm import (
    WakeAlarm,
    main,
)

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
        patch("python_pkg.wake_alarm._alarm.tk", mock),
        patch(
            "python_pkg.wake_alarm._alarm.GateRoot",
            return_value=mock.Tk.return_value,
        ),
    ):
        yield mock


@pytest.fixture(autouse=True)
def _block_extra_devices() -> Generator[MagicMock]:
    """Prevent real subprocess.Popen calls for extra ALSA devices."""
    with (
        patch("python_pkg.wake_alarm._alarm._play_on_extra_devices") as mock,
        patch("python_pkg.wake_alarm._alarm._max_fans", return_value=False),
        patch("python_pkg.wake_alarm._alarm._restore_fans"),
        patch("python_pkg.wake_alarm._alarm._set_max_brightness"),
        patch("python_pkg.wake_alarm._alarm._wake_display"),
        patch("python_pkg.wake_alarm._alarm._warn_if_no_real_sink"),
        patch("python_pkg.wake_alarm._alarm._activate_alarm_audio", return_value=None),
        patch("python_pkg.wake_alarm._alarm._restore_alarm_audio"),
        patch("python_pkg.wake_alarm._alarm.turn_on_plug"),
        patch("python_pkg.wake_alarm._alarm.turn_off_plug"),
    ):
        yield mock


@pytest.fixture
def mock_tk_module() -> Generator[MagicMock]:
    """Provide explicit access to the mocked tk module."""
    mock = _make_mock_tk()
    with (
        patch("python_pkg.wake_alarm._alarm.tk", mock),
        patch(
            "python_pkg.wake_alarm._alarm.GateRoot",
            return_value=mock.Tk.return_value,
        ),
    ):
        yield mock


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestWakeAlarmInit:
    """Tests for WakeAlarm initialization."""

    def test_demo_mode_sets_smaller_window(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """Demo mode still hijacks the full screen — only timers differ."""
        alarm = WakeAlarm(demo_mode=True)
        assert alarm.demo_mode is True
        assert alarm.dismissed is False
        mock_root = mock_tk_module.Tk.return_value
        # LockConfig(mode="soft") never sets overrideredirect (X11 focus bug);
        # fullscreen+topmost are what take over the screen now.
        mock_root.overrideredirect.assert_not_called()
        fs_calls = [
            c
            for c in mock_root.attributes.call_args_list
            if c.kwargs.get("fullscreen") is True
        ]
        assert fs_calls, "fullscreen attribute must be set"
        alarm._stop_beep.set()  # Stop beep thread

    def test_production_mode_fullscreen(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """Production mode activates fullscreen."""
        alarm = WakeAlarm(demo_mode=False)
        assert alarm.demo_mode is False
        mock_root = mock_tk_module.Tk.return_value
        mock_root.overrideredirect.assert_not_called()
        fs_calls = [
            c
            for c in mock_root.attributes.call_args_list
            if c.kwargs.get("fullscreen") is True
        ]
        assert fs_calls, "fullscreen attribute must be set"
        alarm._stop_beep.set()


class TestWakeAlarmDismiss:
    """Tests for alarm dismiss logic."""

    def test_correct_code_dismisses_after_all_rounds(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """Entering the correct answer for every required round dismisses the alarm."""
        from python_pkg.wake_alarm._constants import DISMISS_ROUNDS_REQUIRED

        alarm = WakeAlarm(demo_mode=True)
        mock_entry = mock_tk_module.Entry.return_value

        with patch(
            "python_pkg.wake_alarm._alarm.save_wake_state",
        ) as mock_save:
            for _ in range(DISMISS_ROUNDS_REQUIRED):
                mock_entry.get.return_value = alarm._progress.current_challenge.answer
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
        mock_entry = mock_tk_module.Entry.return_value
        mock_entry.get.return_value = alarm._progress.current_challenge.answer

        alarm._on_submit()

        assert alarm.dismissed is False
        assert alarm._progress.rounds_completed == 1
        alarm._stop_beep.set()

    def test_first_round_correct_non_flash_next_no_countdown(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """When next challenge is math, no flash countdown is started."""
        from python_pkg.wake_alarm._challenges import _Challenge

        alarm = WakeAlarm(demo_mode=True)
        mock_entry = mock_tk_module.Entry.return_value
        mock_entry.get.return_value = alarm._progress.current_challenge.answer
        next_math = _Challenge(kind="math", display="2 + 2 = ?", answer="4", hint="x")
        with patch(
            "python_pkg.wake_alarm._alarm._make_challenge", return_value=next_math
        ):
            alarm._on_submit()

        assert alarm._progress.current_challenge.kind == "math"
        assert alarm.dismissed is False
        alarm._stop_beep.set()

    def test_wrong_code_does_not_dismiss(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """Entering the wrong answer shows an error without dismissing."""
        from python_pkg.wake_alarm._alarm import _Challenge

        alarm = WakeAlarm(demo_mode=True)
        # Use a pinned math challenge so the non-flash wrong-answer branch is covered.
        alarm._progress.current_challenge = _Challenge(
            kind="math", display="2 + 2 = ?", answer="4", hint="test"
        )
        mock_entry = mock_tk_module.Entry.return_value
        mock_entry.get.return_value = "99"

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
            "python_pkg.wake_alarm._alarm.save_wake_state",
        ) as mock_save:
            alarm._on_skip_window_expired()

        # Alarm stays active and audible; only the skip reward is gone.
        assert alarm._progress.skip_earnable is False
        assert alarm._active is True
        assert alarm.dismissed is False
        assert not alarm._stop_beep.is_set()
        mock_save.assert_not_called()
        alarm._view.info_label.configure.assert_called()
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
        from python_pkg.wake_alarm._constants import DISMISS_ROUNDS_REQUIRED

        alarm = WakeAlarm(demo_mode=True)
        alarm._progress.skip_earnable = False
        mock_entry = mock_tk_module.Entry.return_value

        with patch(
            "python_pkg.wake_alarm._alarm.save_wake_state",
        ) as mock_save:
            for _ in range(DISMISS_ROUNDS_REQUIRED):
                mock_entry.get.return_value = alarm._progress.current_challenge.answer
                alarm._on_submit()

        assert alarm.dismissed is True
        assert mock_save.call_args[1]["skip_workout"] is False
        alarm._stop_beep.set()


class TestMain:
    """Tests for the main() entry point."""

    def test_exits_when_not_alarm_day(self) -> None:
        """main() returns early when not an alarm day."""
        with (
            patch(
                "python_pkg.wake_alarm._alarm._should_run_alarm",
                return_value=False,
            ),
            patch("python_pkg.wake_alarm._alarm.sys") as mock_sys,
        ):
            mock_sys.argv = ["alarm"]
            main()  # Should just return without error

    def test_creates_alarm_when_should_run(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """main() creates a WakeAlarm when conditions are met."""
        del mock_tk_module
        with (
            patch(
                "python_pkg.wake_alarm._alarm._should_run_alarm",
                return_value=True,
            ),
            patch(
                "python_pkg.wake_alarm._alarm.sys",
            ) as mock_sys,
            patch.object(WakeAlarm, "run") as mock_run,
            patch.object(WakeAlarm, "__init__", return_value=None),
        ):
            mock_sys.argv = ["alarm"]
            main()
            mock_run.assert_called_once()

    def test_trigger_now_bypasses_gate(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """--trigger-now bypasses _should_run_alarm."""
        del mock_tk_module
        with (
            patch(
                "python_pkg.wake_alarm._alarm._should_run_alarm",
                return_value=False,
            ) as mock_gate,
            patch("python_pkg.wake_alarm._alarm.sys") as mock_sys,
            patch.object(WakeAlarm, "run") as mock_run,
            patch.object(WakeAlarm, "__init__", return_value=None),
        ):
            mock_sys.argv = ["alarm", "--trigger-now"]
            main()
            mock_gate.assert_not_called()
            mock_run.assert_called_once()


class TestCodeRefreshAndTimer:
    """Tests for code refresh and timer update methods."""

    def test_code_refresh_changes_challenge(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """Code refresh generates a new challenge each call."""
        alarm = WakeAlarm(demo_mode=True)
        displays = set()
        for _ in range(50):
            alarm._schedule_code_refresh()
            displays.add(alarm._progress.current_challenge.display)
        assert len(displays) > 1
        alarm._stop_beep.set()

    def test_code_refresh_noop_when_not_active(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """Code refresh is a no-op when alarm is no longer active."""
        alarm = WakeAlarm(demo_mode=True)
        alarm._active = False
        old_challenge = alarm._progress.current_challenge
        alarm._schedule_code_refresh()
        assert alarm._progress.current_challenge is old_challenge
        alarm._stop_beep.set()

    def test_update_timer_noop_when_not_active(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """Timer update is a no-op when alarm is inactive."""
        alarm = WakeAlarm(demo_mode=True)
        alarm._active = False
        alarm._update_timer()  # Should not raise
        alarm._stop_beep.set()


class TestBeepLoop:
    """Tests for the beep loop thread."""

    def test_beep_loop_stops_on_event(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """Beep loop exits when stop event is set."""
        alarm = WakeAlarm(demo_mode=True)
        alarm._stop_beep.set()
        # Loop should exit immediately
        with patch(
            "python_pkg.wake_alarm._alarm._beep_soft",
        ):
            alarm._beep_loop()
        alarm._stop_beep.set()


class TestScreenFlash:
    """Tests for _start_screen_flash and _flash_step."""

    def test_flash_step_shows_dark_on_flash_off(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """When _flash_on=False, the background is set to dark colour."""
        alarm = WakeAlarm(demo_mode=True)
        mock_root = mock_tk_module.Tk.return_value
        mock_root.configure.reset_mock()
        mock_root.after.reset_mock()

        alarm._progress.flash_on = False
        alarm._flash_step()

        mock_root.configure.assert_called_once_with(bg="#1a1a1a")
        assert alarm._progress.flash_on is True
        mock_root.after.assert_called_with(750, alarm._flash_step)
        alarm._stop_beep.set()

    def test_flash_step_shows_red_on_flash_on(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """When _flash_on=True, the background is set to red."""
        alarm = WakeAlarm(demo_mode=True)
        mock_root = mock_tk_module.Tk.return_value
        mock_root.configure.reset_mock()
        mock_root.after.reset_mock()

        alarm._progress.flash_on = True
        alarm._flash_step()

        mock_root.configure.assert_called_once_with(bg="#ff0000")
        assert alarm._progress.flash_on is False
        mock_root.after.assert_called_with(750, alarm._flash_step)
        alarm._stop_beep.set()

    def test_flash_step_stops_when_inactive(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """When alarm is no longer active, _flash_step returns without scheduling."""
        alarm = WakeAlarm(demo_mode=True)
        mock_root = mock_tk_module.Tk.return_value
        alarm._active = False
        mock_root.configure.reset_mock()
        mock_root.after.reset_mock()

        alarm._flash_step()

        mock_root.configure.assert_not_called()
        mock_root.after.assert_not_called()
        alarm._stop_beep.set()
