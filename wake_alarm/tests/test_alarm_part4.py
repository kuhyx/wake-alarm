"""Tests for WakeAlarm's gatelock hooks: on_focus_ready, on_callback_error, on_close."""

from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

if TYPE_CHECKING:
    from collections.abc import Generator

from python_pkg.wake_alarm._alarm import WakeAlarm

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
        patch("python_pkg.wake_alarm._alarm._restore_display"),
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


class TestGatelockHooks:
    """Tests for the LockWindowHooks callbacks (on_focus_ready/on_callback_error)."""

    def test_on_focus_ready_focuses_entry(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """on_focus_ready forces focus onto the dismiss-code entry."""
        del mock_tk_module
        alarm = WakeAlarm(demo_mode=True)
        alarm._view.entry.focus_force.reset_mock()
        alarm.on_focus_ready()
        alarm._view.entry.focus_force.assert_called_once()
        alarm._stop_beep.set()

    def test_on_callback_error_surfaces_and_refocuses(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """on_callback_error shows a message and refocuses the entry."""
        del mock_tk_module
        alarm = WakeAlarm(demo_mode=True)
        alarm._view.entry.focus_force.reset_mock()
        alarm.on_callback_error()
        alarm._view.status_label.configure.assert_called_with(
            text="Something went wrong — try again.",
        )
        alarm._view.entry.focus_force.assert_called_once()
        alarm._stop_beep.set()


class TestClose:
    """Tests for the alarm's gatelock close path (LockWindow.close/on_close)."""

    def test_lock_close_stops_beep_and_destroys(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """LockWindow.close() runs on_close (stop event) and destroys root."""
        del mock_tk_module
        alarm = WakeAlarm(demo_mode=True)
        alarm._lock.close()
        assert alarm._stop_beep.is_set()
        alarm.root.destroy.assert_called()

    def test_on_close_restores_fans(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """on_close calls _restore_fans with the saved fan state."""
        del mock_tk_module
        alarm = WakeAlarm(demo_mode=True)
        alarm._hardware.fan_state = True
        with patch("python_pkg.wake_alarm._alarm._restore_fans") as mock_restore:
            alarm.on_close()
        mock_restore.assert_called_once_with(active=True)
        alarm._stop_beep.set()

    def test_on_close_restores_audio(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """on_close restores the default sink captured at activation."""
        del mock_tk_module
        alarm = WakeAlarm(demo_mode=True)
        alarm._hardware.audio_restore = "jbl_sink"
        with patch(
            "python_pkg.wake_alarm._alarm._restore_alarm_audio",
        ) as mock_restore:
            alarm.on_close()
        mock_restore.assert_called_once_with("jbl_sink")
        alarm._stop_beep.set()
