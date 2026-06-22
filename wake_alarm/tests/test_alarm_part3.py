"""Tests for WakeAlarm — beep loop phases, run, update timer, and flash challenge."""

from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

if TYPE_CHECKING:
    from collections.abc import Generator

from python_pkg.wake_alarm._alarm import (
    WakeAlarm,
)
from python_pkg.wake_alarm._constants import (
    PHASE_MEDIUM_END,
    PHASE_SOFT_END,
)


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
    """Prevent real subprocess calls for extra ALSA devices and hardware."""
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

    def test_run_delegates_to_lock(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """run() hands off to the owned LockWindow.

        Asserts delegation rather than calling the real LockWindow.run(),
        which installs real SIGTERM/SIGINT handlers in the test process.
        """
        del mock_tk_module
        alarm = WakeAlarm(demo_mode=True)
        with patch.object(alarm._lock, "run") as mock_run:
            alarm.run()
        mock_run.assert_called_once_with()
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
        text = alarm._view.timer_label.configure.call_args[1]["text"]
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
        text = alarm._view.timer_label.configure.call_args[1]["text"]
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
        alarm._view.timer_label.configure.reset_mock()
        alarm._update_timer()
        alarm._view.timer_label.configure.assert_not_called()
        alarm._stop_beep.set()


class TestFlashChallenge:
    """Tests for flash challenge countdown behaviour inside WakeAlarm."""

    def test_flash_tick_counts_down_and_hides(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """_flash_tick counts down per second and hides the code at zero."""
        from python_pkg.wake_alarm._alarm import _Challenge

        alarm = WakeAlarm(demo_mode=True)
        alarm._progress.current_challenge = _Challenge(
            kind="flash",
            display="ABCDEFGH",
            answer="ABCDEFGH",
            hint="Memorise",
        )
        alarm._progress.flash_remaining = 2
        alarm._view.status_label.configure.reset_mock()

        alarm._flash_tick()
        assert alarm._progress.flash_remaining == 1
        alarm._view.status_label.configure.assert_called()

        alarm._flash_tick()
        assert alarm._progress.flash_remaining == 0

        # Final tick hides the code.
        alarm._flash_tick()
        # _code_label and _status_label share the same mock; inspect all calls.
        all_texts = [
            c.kwargs.get("text", "")
            for c in alarm._view.code_label.configure.call_args_list
        ]
        assert any("?" in t for t in all_texts)
        alarm._stop_beep.set()

    def test_flash_tick_noop_when_inactive(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """_flash_tick returns immediately when the alarm is no longer active."""
        alarm = WakeAlarm(demo_mode=True)
        alarm._active = False
        alarm._progress.flash_remaining = 3
        alarm._view.status_label.configure.reset_mock()

        alarm._flash_tick()

        alarm._view.status_label.configure.assert_not_called()
        alarm._stop_beep.set()

    def test_wrong_flash_answer_reshows_code(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """Wrong flash answer restores the code and restarts the countdown."""
        from python_pkg.wake_alarm._alarm import _Challenge

        alarm = WakeAlarm(demo_mode=True)
        alarm._progress.current_challenge = _Challenge(
            kind="flash",
            display="TESTCODE",
            answer="TESTCODE",
            hint="Memorise",
        )
        mock_entry = mock_tk_module.Entry.return_value
        mock_entry.get.return_value = "WRONGCODE"
        alarm._view.code_label.configure.reset_mock()

        alarm._on_submit()

        assert alarm.dismissed is False
        # Code label should be reconfigured (code shown again + countdown restarted).
        alarm._view.code_label.configure.assert_called()
        alarm._stop_beep.set()

    def test_next_round_flash_starts_countdown(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """When the next-round challenge is flash, the countdown starts immediately."""
        from python_pkg.wake_alarm._alarm import _Challenge

        alarm = WakeAlarm(demo_mode=True)
        alarm._progress.current_challenge = _Challenge(
            kind="math", display="2 + 2 = ?", answer="4", hint="test"
        )
        next_flash = _Challenge(
            kind="flash", display="ABCDEFGH", answer="ABCDEFGH", hint="Memorise"
        )
        mock_entry = mock_tk_module.Entry.return_value
        mock_entry.get.return_value = "4"

        with patch(
            "python_pkg.wake_alarm._alarm._make_challenge", return_value=next_flash
        ):
            alarm._on_submit()

        assert alarm._progress.current_challenge.kind == "flash"
        assert alarm.dismissed is False
        alarm._stop_beep.set()


class TestDismissWithoutSkip:
    """Tests for alarm dismiss without earning skip."""

    def test_dismiss_without_skip_shows_no_skip_message(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """Dismissing with earned_skip=False shows appropriate message."""
        del mock_tk_module
        alarm = WakeAlarm(demo_mode=True)
        mock_widget = MagicMock()
        alarm._view.container.winfo_children.return_value = [mock_widget]

        with patch(
            "python_pkg.wake_alarm._alarm.save_wake_state",
        ) as mock_save:
            alarm._dismiss_alarm(earned_skip=False)

        assert alarm.dismissed is True
        mock_save.assert_called_once()
        assert mock_save.call_args[1]["skip_workout"] is False
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

        alarm._view.status_label.configure.assert_called_with(
            text="No workout skip today.",
        )
        alarm._stop_beep.set()
