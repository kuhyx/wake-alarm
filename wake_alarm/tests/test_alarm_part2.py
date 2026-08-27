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

    def test_init_starts_sink_reactivation(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """The retry runs, and stops when the alarm does.

        Without this the HDMI sink stays absent for the whole alarm: its card
        profile is ``off`` at wake time, and only a fresh set-card-profile can
        bring the sink into existence -- re-enumerating sinks never finds it.
        The conftest stub is replaced here so the wiring itself is asserted.
        """
        assert mock_tk_module is not None
        with patch("wake_alarm._alarm.start_alarm_reactivation") as start:
            alarm = WakeAlarm(demo_mode=True)
        start.assert_called_once_with(alarm._stop_beep)
        # The same event the beep loop watches, so dismissal ends both.
        alarm._stop_beep.set()
        assert start.call_args.args[0].is_set()

    def test_init_takes_the_power_key_inhibitor(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """A short power-button press must not end the alarm in one tap."""
        assert mock_tk_module is not None
        with patch("wake_alarm._alarm.take_power_key_inhibitor") as take:
            alarm = WakeAlarm(demo_mode=True)
        take.assert_called_once_with()
        assert alarm._hardware.inhibitor is take.return_value
        alarm._stop_beep.set()

    def test_init_opens_a_session_record(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """Written while ringing, so a power cut leaves a trace to re-fire on."""
        assert mock_tk_module is not None
        with patch("wake_alarm._alarm.start_session") as start:
            alarm = WakeAlarm(demo_mode=True)
        start.assert_called_once()
        # The correlation id joins this record to the JSONL log with no
        # handshake -- both sides derive it from the same alarm instant.
        assert start.call_args.args[0].startswith("wake-")
        alarm._stop_beep.set()

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
