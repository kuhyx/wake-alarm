"""Tests for WakeAlarm's gatelock hooks: on_focus_ready, on_callback_error, on_close."""

from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

if TYPE_CHECKING:
    from collections.abc import Generator

from wake_alarm._alarm import WakeAlarm
from wake_alarm._alarm_view import _EntryProxy
from wake_alarm._sinks import _AudioState
from wake_alarm.tests.conftest import TWO_OUTPUTS

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


class TestGatelockHooks:
    """Tests for the LockWindowHooks callbacks (on_focus_ready/on_callback_error)."""

    def test_on_focus_ready_focuses_entry(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """on_focus_ready forces focus onto the dismiss-code entry."""
        del mock_tk_module
        alarm = WakeAlarm(demo_mode=True)
        alarm._view._views[0].entry.focus_force.reset_mock()
        alarm.on_focus_ready(alarm._view._views[0])
        alarm._view._views[0].entry.focus_force.assert_called_once()
        alarm._stop_beep.set()

    def test_on_callback_error_surfaces_and_refocuses(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """on_callback_error shows a message and refocuses the entry."""
        del mock_tk_module
        alarm = WakeAlarm(demo_mode=True)
        alarm._view._views[0].entry.focus_force.reset_mock()
        alarm.on_callback_error()
        alarm._view._views[0].labels.status.configure.assert_called_with(
            text="Something went wrong — try again.",
        )
        alarm._view._views[0].entry.focus_force.assert_called_once()
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
        with patch("wake_alarm._alarm._restore_fans") as mock_restore:
            alarm.on_close()
        mock_restore.assert_called_once_with(active=True)
        alarm._stop_beep.set()

    def test_on_close_restores_audio(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """on_close restores the audio state captured at activation."""
        del mock_tk_module
        alarm = WakeAlarm(demo_mode=True)
        state = _AudioState(
            default_sink="jbl_sink",
            card_profiles={},
            sink_volumes={},
            sink_mutes={},
        )
        alarm._hardware.audio_restore = state
        with patch(
            "wake_alarm._alarm._restore_audio_state",
        ) as mock_restore:
            alarm.on_close()
        mock_restore.assert_called_once_with(state)
        alarm._stop_beep.set()


class TestMultiMonitorSurfaces:
    """Per-output behaviour added in the gatelock v0.2.0 migration."""

    def test_on_focus_ready_with_no_live_output(
        self, mock_tk_module: MagicMock
    ) -> None:
        """A dark machine arms the alarm with nothing to focus."""
        del mock_tk_module
        alarm = WakeAlarm(demo_mode=True)
        alarm._view._views[0].entry.focus_force.reset_mock()

        alarm.on_focus_ready(None)

        alarm._view._views[0].entry.focus_force.assert_not_called()
        alarm._stop_beep.set()

    def test_focus_force_skips_destroyed_entries(
        self, mock_tk_module: MagicMock
    ) -> None:
        """A surface whose window already died is stepped over."""
        del mock_tk_module
        alarm = WakeAlarm(demo_mode=True)
        dead, alive = MagicMock(), MagicMock()
        dead.focus_force.side_effect = tk.TclError("gone")
        proxy = _EntryProxy([dead, alive], MagicMock())

        proxy.focus_force()

        alive.focus_force.assert_called_once_with()
        alarm._stop_beep.set()

    def test_title_label_fans_out(self, mock_tk_module: MagicMock) -> None:
        """Every named label proxy reaches its per-monitor copies."""
        del mock_tk_module
        alarm = WakeAlarm(demo_mode=True)

        alarm._view.title_label.configure(text="hi")

        alarm._view._views[0].labels.title.configure.assert_called_with(text="hi")
        alarm._stop_beep.set()

    def test_teardown_forgets_a_dark_output(self, mock_tk_module: MagicMock) -> None:
        """An output going dark drops just its own view."""
        del mock_tk_module
        alarm = WakeAlarm(demo_mode=True)
        surface = alarm._view._views[0]

        alarm.teardown_surface(surface)

        assert alarm._view._views == []
        alarm._stop_beep.set()

    def test_focus_force_when_every_entry_is_gone(
        self, mock_tk_module: MagicMock
    ) -> None:
        """All surfaces destroyed: nothing to focus, and no exception."""
        del mock_tk_module
        alarm = WakeAlarm(demo_mode=True)
        dead = MagicMock()
        dead.focus_force.side_effect = tk.TclError("gone")

        _EntryProxy([dead], MagicMock()).focus_force()  # must not raise

        alarm._stop_beep.set()


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
