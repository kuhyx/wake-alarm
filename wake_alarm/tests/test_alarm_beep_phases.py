"""Tests for the beep escalation loop's phase selection."""

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
from wake_alarm._constants import (
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

        # Midpoint of the medium band, not "one past the soft boundary": the
        # phases are tuned to fit inside the failsafe window, so an offset
        # anchored to one edge can land in the next phase entirely.
        midpoint = (PHASE_SOFT_END + PHASE_MEDIUM_END) / 2
        alarm._progress.started_at = time_mod.monotonic() - midpoint * 60

        call_count = 0

        def stop_after_one(*_args: object, **_kwargs: object) -> None:
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                alarm._stop_beep.set()

        with (
            patch(
                "wake_alarm._alarm._beep_medium",
                side_effect=stop_after_one,
            ) as mock_beep,
            # Any other rung also ends the loop, so a mistuned phase boundary
            # fails this test instead of spinning forever on the real audio
            # stack -- which previously hung the entire suite.
            patch("wake_alarm._alarm._beep_soft", side_effect=stop_after_one),
            patch("wake_alarm._alarm._beep_loud", side_effect=stop_after_one),
            patch("wake_alarm._alarm._play_on_all_sinks"),
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

        alarm._progress.started_at = time_mod.monotonic() - (PHASE_MEDIUM_END + 1) * 60

        call_count = 0

        def stop_after_one(*_args: object, **_kwargs: object) -> None:
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                alarm._stop_beep.set()

        with (
            patch(
                "wake_alarm._alarm._beep_loud",
                side_effect=stop_after_one,
            ) as mock_beep,
            # See the note in test_medium_phase: any rung must end the loop.
            patch("wake_alarm._alarm._beep_soft", side_effect=stop_after_one),
            patch("wake_alarm._alarm._beep_medium", side_effect=stop_after_one),
            patch("wake_alarm._alarm._play_on_all_sinks"),
        ):
            alarm._beep_loop()

        mock_beep.assert_called()
        alarm._stop_beep.set()
