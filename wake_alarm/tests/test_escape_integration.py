"""Tests wiring the escape hatch into the running alarm.

Split from ``test_escape_flow`` for the 250-line cap: that module covers the
hatch in isolation, this one covers it mounted on a real two-monitor alarm.
"""

from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from gatelock import EscapePolicy, EscapeTracker
import pytest

from wake_alarm._alarm import WakeAlarm
from wake_alarm._constants import ESCAPE_OFFER_AFTER_SECONDS
from wake_alarm.tests.conftest import TWO_OUTPUTS

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

TODAY = "2026-07-25"


@pytest.fixture
def tracker(tmp_path: Path) -> EscapeTracker:
    """A tracker over a throwaway history and key."""
    key = tmp_path / "hmac.key"
    key.write_bytes(b"0" * 32)
    return EscapeTracker(
        EscapePolicy(name="cant-wake", label="Can't-wake"),
        tmp_path / "escape.json",
        key_file=key,
    )


# ---------------------------------------------------------------------------
# Tk stand-ins (duplicated from the part files so this one is self-contained;
# they are autouse there, and hoisting them into conftest would silently
# neuter the audio and sync suites)
# ---------------------------------------------------------------------------


def _make_mock_tk() -> MagicMock:
    """Build a MagicMock that stands in for the tkinter module.

    ``Button`` gets a ``side_effect`` rather than a single ``return_value``:
    every surface must end up with its *own* button, otherwise
    ``escape_buttons`` is N references to one mock and "packed on every
    monitor" cannot be told apart from "packed once".
    """
    mock = MagicMock()
    mock_root = MagicMock()
    mock_root.winfo_screenwidth.return_value = 1920
    mock_root.winfo_screenheight.return_value = 1080
    mock.Tk.return_value = mock_root
    mock.Frame.side_effect = lambda *_args, **_kwargs: MagicMock()
    mock.Label.return_value = MagicMock()
    mock.Entry.return_value = MagicMock()
    mock.Button.side_effect = lambda *_args, **_kwargs: MagicMock()
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
        patch("wake_alarm._alarm.GateRoot", return_value=mock.Tk.return_value),
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


@pytest.mark.usefixtures("dual_output")
class TestAlarmIntegration:
    """The hatch as the alarm actually uses it, on a two-monitor desk."""

    def test_every_output_gets_its_own_button(self) -> None:
        """The premise the rest of this class rests on: two distinct buttons."""
        alarm = WakeAlarm(demo_mode=True)

        buttons = alarm._view.escape_buttons
        assert len(buttons) == len(TWO_OUTPUTS)
        assert len({id(button) for button in buttons}) == len(TWO_OUTPUTS)
        alarm._stop_beep.set()

    def test_button_hidden_until_earned(self) -> None:
        """Straight after the alarm starts, the hatch is not offered."""
        alarm = WakeAlarm(demo_mode=True)
        for button in alarm._view.escape_buttons:
            button.pack.reset_mock()

        alarm._update_timer()

        for button in alarm._view.escape_buttons:
            button.pack.assert_not_called()
        alarm._stop_beep.set()

    def test_button_revealed_once_earned(self) -> None:
        """After the threshold the button appears on every monitor.

        Driven through ``_update_timer`` rather than the hatch directly, so
        the per-second tick is on the hook for ever offering the hatch at all.
        """
        alarm = WakeAlarm(demo_mode=True)
        alarm._progress.started_at -= ESCAPE_OFFER_AFTER_SECONDS + 10
        for button in alarm._view.escape_buttons:
            button.pack.reset_mock()

        alarm._update_timer()

        for button in alarm._view.escape_buttons:
            button.pack.assert_called()
        alarm._stop_beep.set()

    def test_not_reoffered_while_open(self) -> None:
        """With the form already up, the button is not re-packed."""
        alarm = WakeAlarm(demo_mode=True)
        alarm._progress.started_at -= ESCAPE_OFFER_AFTER_SECONDS + 10
        alarm._escape.is_open = True
        for button in alarm._view.escape_buttons:
            button.pack.reset_mock()

        alarm._update_timer()

        for button in alarm._view.escape_buttons:
            button.pack.assert_not_called()
        alarm._stop_beep.set()

    def test_open_swaps_every_surface(self) -> None:
        """Opening the form hides the challenge and builds a form per monitor."""
        alarm = WakeAlarm(demo_mode=True)
        surfaces = alarm._view.surfaces
        assert len(surfaces) == len(TWO_OUTPUTS)

        with patch("wake_alarm._escape_flow.EscapeDialog") as dialog_cls:
            alarm._escape.open()

        assert alarm._escape.is_open is True
        assert dialog_cls.call_count == len(surfaces)
        # One dialog *per* container, not two against the same parent.
        parents = [call.args[0] for call in dialog_cls.call_args_list]
        assert {id(parent) for parent in parents} == {
            id(view.container) for view in surfaces
        }
        for view in surfaces:
            view.challenge_frame.pack_forget.assert_called_once_with()
        alarm._stop_beep.set()

    def test_a_dead_surface_does_not_block_the_others(self) -> None:
        """A monitor that has gone away raises TclError; the rest still swap."""
        alarm = WakeAlarm(demo_mode=True)
        dead, live = alarm._view.surfaces
        dead.challenge_frame.pack_forget.side_effect = tk.TclError("bad path name")

        with patch("wake_alarm._escape_flow.EscapeDialog") as dialog_cls:
            alarm._escape.open()

        assert dialog_cls.call_count == 1
        assert dialog_cls.call_args.args[0] is live.container
        alarm._stop_beep.set()

    def test_cancel_puts_the_challenge_back(self) -> None:
        """Backing out destroys every form and re-packs every challenge.

        The bool alone is not the property that matters: ``open`` took the
        challenge off the screen, so a cancel that only flips a flag leaves
        the alarm showing a dead form on both monitors.
        """
        alarm = WakeAlarm(demo_mode=True)
        surfaces = alarm._view.surfaces
        dialogs: list[MagicMock] = []

        def make_dialog(*_args: object, **_kwargs: object) -> MagicMock:
            dialog = MagicMock()
            dialogs.append(dialog)
            return dialog

        with patch("wake_alarm._escape_flow.EscapeDialog", side_effect=make_dialog):
            alarm._escape.open()
        # The frame was packed once when the view was built; only the re-pack
        # that close() owes us should count.
        for view in surfaces:
            view.challenge_frame.pack.reset_mock()

        alarm._escape.close()

        assert alarm._escape.is_open is False
        assert alarm.dismissed is False
        assert len(dialogs) == len(TWO_OUTPUTS)
        for dialog in dialogs:
            dialog.frame.destroy.assert_called_once_with()
        for view in surfaces:
            view.challenge_frame.pack.assert_called_once_with()
        alarm._stop_beep.set()

    def test_granted_dismisses_without_a_skip(self) -> None:
        """Using the hatch silences the alarm but earns no workout skip."""
        alarm = WakeAlarm(demo_mode=True)

        with patch.object(alarm, "_dismiss_alarm") as dismiss:
            alarm._on_escape_granted()

        dismiss.assert_called_once_with(earned_skip=False)
        alarm._stop_beep.set()
