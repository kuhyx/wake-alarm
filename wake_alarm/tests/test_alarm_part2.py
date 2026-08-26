"""Tests for _alarm.py — WakeAlarm init, dismiss, run, and beep phases (part 2)."""

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
        # Since gatelock v0.2.0 even demo takes overrideredirect: a window
        # manager rewrites a managed window's geometry, so per-output
        # placement is impossible without it. attributes(fullscreen=True)
        # is gone -- explicit per-output geometry replaces it.
        mock_root.overrideredirect.assert_called_with(boolean=True)
        assert alarm._view._views, "a surface must exist per live output"
        alarm._stop_beep.set()  # Stop beep thread

    def test_production_mode_fullscreen(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """Production mode activates fullscreen."""
        alarm = WakeAlarm(demo_mode=False)
        assert alarm.demo_mode is False
        mock_root = mock_tk_module.Tk.return_value
        mock_root.overrideredirect.assert_called_with(boolean=True)
        # attributes(fullscreen=True) is deliberately gone: it is an EWMH
        # request an override-redirect window is invisible to, and where
        # it applies it snaps to one monitor or the whole bounding box.
        assert alarm._view._views, "a surface must exist per live output"
        alarm._stop_beep.set()


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

        mock_root.configure.assert_called_once_with(bg=alarm._view.config.bg)
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

        mock_root.configure.assert_called_once_with(bg=alarm._view.config.danger)
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
