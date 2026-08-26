"""Tests for the flash-challenge dismiss round."""

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
        patch("wake_alarm._alarm_view.tk", mock),
        patch(
            "wake_alarm._alarm.GateRoot",
            return_value=mock.Tk.return_value,
        ),
    ):
        yield mock


@pytest.fixture(autouse=True)
def _block_extra_devices() -> Generator[MagicMock]:
    """Prevent real subprocess calls for extra ALSA devices and hardware."""
    with (
        patch("wake_alarm._alarm._play_on_all_sinks") as mock,
        patch("wake_alarm._alarm._max_fans", return_value=False),
        patch("wake_alarm._alarm._restore_fans"),
        patch("wake_alarm._alarm._set_max_brightness"),
        patch("wake_alarm._alarm._wake_display"),
        patch("wake_alarm._alarm._restore_display"),
        patch("wake_alarm._alarm._warn_if_no_real_sink"),
        patch("wake_alarm._alarm._activate_all_outputs", return_value=None),
        patch("wake_alarm._alarm._restore_audio_state"),
        patch("wake_alarm._alarm.turn_on_plug"),
        patch("wake_alarm._alarm.turn_off_plug"),
    ):
        yield mock


@pytest.fixture
def mock_tk_module() -> Generator[MagicMock]:
    """Provide explicit access to the mocked tk module."""
    mock = _make_mock_tk()
    with (
        patch("wake_alarm._alarm.tk", mock),
        patch("wake_alarm._alarm_view.tk", mock),
        patch(
            "wake_alarm._alarm.GateRoot",
            return_value=mock.Tk.return_value,
        ),
    ):
        yield mock


class TestFlashChallenge:
    """Tests for flash challenge countdown behaviour inside WakeAlarm."""

    def test_flash_tick_counts_down_and_hides(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """_flash_tick counts down per second and hides the code at zero."""
        from wake_alarm._alarm import _Challenge

        alarm = WakeAlarm(demo_mode=True)
        alarm._progress.current_challenge = _Challenge(
            kind="flash",
            display="ABCDEFGH",
            answer="ABCDEFGH",
            hint="Memorise",
        )
        alarm._progress.flash_remaining = 2
        alarm._view._views[0].labels.status.configure.reset_mock()

        alarm._flash_tick()
        assert alarm._progress.flash_remaining == 1
        alarm._view._views[0].labels.status.configure.assert_called()

        alarm._flash_tick()
        assert alarm._progress.flash_remaining == 0

        # Final tick hides the code.
        alarm._flash_tick()
        # _code_label and _status_label share the same mock; inspect all calls.
        all_texts = [
            c.kwargs.get("text", "")
            for c in alarm._view._views[0].labels.code.configure.call_args_list
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
        alarm._view._views[0].labels.status.configure.reset_mock()

        alarm._flash_tick()

        alarm._view._views[0].labels.status.configure.assert_not_called()
        alarm._stop_beep.set()

    def test_wrong_flash_answer_reshows_code(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """Wrong flash answer restores the code and restarts the countdown."""
        from wake_alarm._alarm import _Challenge

        alarm = WakeAlarm(demo_mode=True)
        alarm._progress.current_challenge = _Challenge(
            kind="flash",
            display="TESTCODE",
            answer="TESTCODE",
            hint="Memorise",
        )
        alarm._view.entry_var.get.return_value = "WRONGCODE"
        alarm._view._views[0].labels.code.configure.reset_mock()

        alarm._on_submit()

        assert alarm.dismissed is False
        # Code label should be reconfigured (code shown again + countdown restarted).
        alarm._view._views[0].labels.code.configure.assert_called()
        alarm._stop_beep.set()

    def test_next_round_flash_starts_countdown(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """When the next-round challenge is flash, the countdown starts immediately."""
        from wake_alarm._alarm import _Challenge

        alarm = WakeAlarm(demo_mode=True)
        alarm._progress.current_challenge = _Challenge(
            kind="math", display="2 + 2 = ?", answer="4", hint="test"
        )
        next_flash = _Challenge(
            kind="flash", display="ABCDEFGH", answer="ABCDEFGH", hint="Memorise"
        )
        alarm._view.entry_var.get.return_value = "4"

        with patch("wake_alarm._alarm._make_challenge", return_value=next_flash):
            alarm._on_submit()

        assert alarm._progress.current_challenge.kind == "flash"
        assert alarm.dismissed is False
        alarm._stop_beep.set()
