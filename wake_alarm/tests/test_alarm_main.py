"""Tests for the alarm daemon entry point."""

from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

if TYPE_CHECKING:
    from collections.abc import Generator

from wake_alarm._alarm import (
    WakeAlarm,
    main,
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


class TestMain:
    """Tests for the main() entry point."""

    def test_exits_when_not_alarm_day(self) -> None:
        """main() returns early when not an alarm day."""
        with (
            patch(
                "wake_alarm._alarm.should_run_alarm",
                return_value=False,
            ),
            patch("wake_alarm._alarm.sys") as mock_sys,
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
                "wake_alarm._alarm.should_run_alarm",
                return_value=True,
            ),
            patch(
                "wake_alarm._alarm.sys",
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
                "wake_alarm._alarm.should_run_alarm",
                return_value=False,
            ) as mock_gate,
            patch("wake_alarm._alarm.sys") as mock_sys,
            patch.object(WakeAlarm, "run") as mock_run,
            patch.object(WakeAlarm, "__init__", return_value=None),
        ):
            mock_sys.argv = ["alarm", "--trigger-now"]
            main()
            mock_gate.assert_not_called()
            mock_run.assert_called_once()
