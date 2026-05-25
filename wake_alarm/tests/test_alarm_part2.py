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
from python_pkg.wake_alarm._constants import (
    PHASE_MEDIUM_END,
    PHASE_SOFT_END,
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
    with patch("python_pkg.wake_alarm._alarm.tk", mock):
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
    with patch("python_pkg.wake_alarm._alarm.tk", mock):
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
        # We deliberately drop overrideredirect (X11 focus bug); fullscreen+topmost
        # are what take over the screen now.
        mock_root.overrideredirect.assert_not_called()
        fs_calls = [
            c
            for c in mock_root.attributes.call_args_list
            if c.args and c.args[0] == "-fullscreen"
        ]
        assert fs_calls, "-fullscreen attribute must be set"
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
            if c.args and c.args[0] == "-fullscreen"
        ]
        assert fs_calls, "-fullscreen attribute must be set"
        alarm._stop_beep.set()


class TestWakeAlarmDismiss:
    """Tests for alarm dismiss logic."""

    def test_correct_code_dismisses(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """Entering the correct code dismisses the alarm."""
        alarm = WakeAlarm(demo_mode=True)
        code = alarm._current_code
        mock_entry = mock_tk_module.Entry.return_value
        mock_entry.get.return_value = code

        with patch(
            "python_pkg.wake_alarm._alarm.save_wake_state",
        ) as mock_save:
            alarm._on_submit()

        assert alarm.dismissed is True
        mock_save.assert_called_once()
        call_kwargs = mock_save.call_args[1]
        assert call_kwargs["skip_workout"] is True
        alarm._stop_beep.set()

    def test_wrong_code_does_not_dismiss(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """Entering the wrong code shows error without dismissing."""
        alarm = WakeAlarm(demo_mode=True)
        mock_entry = mock_tk_module.Entry.return_value
        mock_entry.get.return_value = "000000"
        # Ensure current code is different
        alarm._current_code = "123456"

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
        assert alarm._skip_earnable is False
        assert alarm._active is True
        assert alarm.dismissed is False
        assert not alarm._stop_beep.is_set()
        mock_save.assert_not_called()
        alarm._info_label.configure.assert_called()
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
        assert alarm._skip_earnable is True
        alarm._stop_beep.set()

    def test_dismiss_after_skip_window_earns_no_skip(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """Typing the code after the skip window stops the alarm w/o a skip."""
        alarm = WakeAlarm(demo_mode=True)
        alarm._skip_earnable = False
        code = alarm._current_code
        mock_entry = mock_tk_module.Entry.return_value
        mock_entry.get.return_value = code

        with patch(
            "python_pkg.wake_alarm._alarm.save_wake_state",
        ) as mock_save:
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

    def test_code_refresh_changes_code(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """Code refresh generates a new code."""
        alarm = WakeAlarm(demo_mode=True)
        # Call refresh many times — at least one should differ
        codes = set()
        for _ in range(50):
            alarm._schedule_code_refresh()
            codes.add(alarm._current_code)
        assert len(codes) > 1
        alarm._stop_beep.set()

    def test_code_refresh_noop_when_not_active(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """Code refresh is a no-op when alarm is no longer active."""
        alarm = WakeAlarm(demo_mode=True)
        alarm._active = False
        old_code = alarm._current_code
        alarm._schedule_code_refresh()
        # Code doesn't change because _active=False causes early return
        assert alarm._current_code == old_code
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


class TestClose:
    """Tests for the alarm close path."""

    def test_close_stops_beep_and_destroys(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """_close sets stop event and destroys root."""
        del mock_tk_module
        alarm = WakeAlarm(demo_mode=True)
        alarm._close()
        assert alarm._stop_beep.is_set()
        alarm.root.destroy.assert_called()

    def test_close_restores_fans(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """_close calls _restore_fans with the saved fan state."""
        del mock_tk_module
        alarm = WakeAlarm(demo_mode=True)
        alarm._fan_state = True
        with patch("python_pkg.wake_alarm._alarm._restore_fans") as mock_restore:
            alarm._close()
        mock_restore.assert_called_once_with(active=True)

    def test_close_restores_audio(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """_close restores the default sink captured at activation."""
        del mock_tk_module
        alarm = WakeAlarm(demo_mode=True)
        alarm._audio_restore = "jbl_sink"
        with patch(
            "python_pkg.wake_alarm._alarm._restore_alarm_audio",
        ) as mock_restore:
            alarm._close()
        mock_restore.assert_called_once_with("jbl_sink")
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

        alarm._flash_on = False
        alarm._flash_step()

        mock_root.configure.assert_called_once_with(bg="#1a1a1a")
        assert alarm._flash_on is True
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

        alarm._flash_on = True
        alarm._flash_step()

        mock_root.configure.assert_called_once_with(bg="#ff0000")
        assert alarm._flash_on is False
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


class TestDismissWithoutSkip:
    """Tests for alarm dismiss without earning skip."""

    def test_dismiss_without_skip_shows_no_skip_message(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """Dismissing with earned_skip=False shows appropriate message."""
        alarm = WakeAlarm(demo_mode=True)
        # Simulate existing child widgets
        mock_widget = MagicMock()
        alarm._container.winfo_children.return_value = [mock_widget]

        with patch(
            "python_pkg.wake_alarm._alarm.save_wake_state",
        ) as mock_save:
            alarm._dismiss_alarm(earned_skip=False)

        assert alarm.dismissed is True
        mock_save.assert_called_once()
        call_kwargs = mock_save.call_args[1]
        assert call_kwargs["skip_workout"] is False
        mock_widget.destroy.assert_called_once()
        alarm._stop_beep.set()


class TestSkipWindowExpiredMessage:
    """Tests for the on-screen message when the skip window expires."""

    def test_expired_updates_status_label(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """Expiry updates the status label instead of closing the alarm."""
        del mock_tk_module
        alarm = WakeAlarm(demo_mode=True)

        alarm._on_skip_window_expired()

        alarm._status_label.configure.assert_called_with(
            text="No workout skip today.",
        )
        alarm._stop_beep.set()


class TestBeepLoopPhases:
    """Tests for different beep loop escalation phases."""

    def test_medium_phase(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """Beep loop enters medium phase after PHASE_SOFT_END minutes."""
        alarm = WakeAlarm(demo_mode=True)
        # Set alarm start to make elapsed > PHASE_SOFT_END minutes
        import time as time_mod

        alarm._alarm_start = time_mod.monotonic() - (PHASE_SOFT_END + 1) * 60

        call_count = 0

        def stop_after_one(*_args: object, **_kwargs: object) -> None:
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                alarm._stop_beep.set()

        with (
            patch(
                "python_pkg.wake_alarm._alarm._beep_medium",
                side_effect=stop_after_one,
            ) as mock_beep,
        ):
            alarm._beep_loop()

        mock_beep.assert_called()
        alarm._stop_beep.set()

    def test_loud_phase(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """Beep loop enters loud phase after PHASE_MEDIUM_END minutes."""
        alarm = WakeAlarm(demo_mode=True)
        import time as time_mod

        alarm._alarm_start = time_mod.monotonic() - (PHASE_MEDIUM_END + 1) * 60

        call_count = 0

        def stop_after_one(*_args: object, **_kwargs: object) -> None:
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                alarm._stop_beep.set()

        with (
            patch(
                "python_pkg.wake_alarm._alarm._beep_loud",
                side_effect=stop_after_one,
            ) as mock_beep,
        ):
            alarm._beep_loop()

        mock_beep.assert_called()
        alarm._stop_beep.set()


class TestRunMethod:
    """Tests for the run() method."""

    def test_run_calls_mainloop(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """run() calls root.mainloop()."""
        alarm = WakeAlarm(demo_mode=True)
        alarm.run()
        alarm.root.mainloop.assert_called_once()
        alarm._stop_beep.set()


class TestUpdateTimerActive:
    """Tests for timer update when alarm is active."""

    def test_update_timer_shows_skip_window(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """While the skip is earnable, the timer shows the skip-window count."""
        del mock_tk_module
        alarm = WakeAlarm(demo_mode=True)
        alarm._update_timer()
        text = alarm._timer_label.configure.call_args[1]["text"]
        assert text.startswith("Skip window:")
        alarm._stop_beep.set()

    def test_update_timer_shows_prompt_after_window(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """After the window the timer shows the silence prompt and keeps going."""
        import time as time_mod

        alarm = WakeAlarm(demo_mode=True)
        # Far in the past so remaining == 0 -> the else branch.
        alarm._alarm_start = time_mod.monotonic() - 60 * 60
        alarm.root.after.reset_mock()
        alarm._update_timer()
        text = alarm._timer_label.configure.call_args[1]["text"]
        assert "type the code" in text
        # The alarm keeps nagging: it always reschedules while active.
        alarm.root.after.assert_called_once()
        alarm._stop_beep.set()

    def test_update_timer_noop_when_not_active(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """Timer update is a no-op once the alarm is no longer active."""
        del mock_tk_module
        alarm = WakeAlarm(demo_mode=True)
        alarm._active = False
        alarm._timer_label.configure.reset_mock()
        alarm._update_timer()
        alarm._timer_label.configure.assert_not_called()
        alarm._stop_beep.set()
