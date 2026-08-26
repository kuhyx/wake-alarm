"""Tests that every action reaches all monitors."""

from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

if TYPE_CHECKING:
    from collections.abc import Generator

from wake_alarm._alarm import WakeAlarm
from wake_alarm.tests.conftest import TWO_OUTPUTS

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


@pytest.mark.usefixtures("dual_output")
class TestFanOutAcrossMonitors:
    """The three remaining v0.2.0 loops, on a desk that actually has two.

    Under the single-output default every one of these assertions holds even
    if the loop body only ever ran for ``containers[0]`` -- which is exactly
    the regression per-output locking exists to prevent.
    """

    def test_dismiss_clears_and_repaints_every_monitor(
        self, mock_tk_module: MagicMock
    ) -> None:
        """The dismissal message replaces the challenge on both screens."""
        alarm = WakeAlarm(demo_mode=True)
        containers = alarm._view.containers
        assert len(containers) == len(TWO_OUTPUTS)
        leftovers = {id(c): [MagicMock(), MagicMock()] for c in containers}
        for container in containers:
            container.winfo_children.return_value = leftovers[id(container)]
        mock_tk_module.Label.reset_mock()

        with patch("wake_alarm._alarm.save_wake_state"):
            alarm._dismiss_alarm(earned_skip=True)

        for widgets in leftovers.values():
            for widget in widgets:
                widget.destroy.assert_called_once_with()
        parents = [call.args[0] for call in mock_tk_module.Label.call_args_list]
        assert {id(parent) for parent in parents} == {id(c) for c in containers}
        alarm._stop_beep.set()

    def test_flash_recolours_every_monitor(self, mock_tk_module: MagicMock) -> None:
        """A flash tick reaches both surfaces, not just the primary."""
        del mock_tk_module
        alarm = WakeAlarm(demo_mode=True)
        containers = alarm._view.containers
        # __init__ already ran one flash tick; only the next one should count.
        for container in containers:
            container.configure.reset_mock()
            container.winfo_toplevel.return_value.configure.reset_mock()

        alarm._flash_step()

        for container in containers:
            container.configure.assert_called_once()
            container.winfo_toplevel.return_value.configure.assert_called_once()
        alarm._stop_beep.set()
