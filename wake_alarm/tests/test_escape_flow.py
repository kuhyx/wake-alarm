"""Tests for the alarm's escape hatch.

The alarm was the only locker with no way out but the challenge itself. These
tests pin the two properties that make the new hatch safe: it is never the
*easy* first move, and it cannot be leaned on repeatedly.
"""

from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from gatelock import EscapePolicy, EscapeTracker
import pytest

from wake_alarm._constants import ESCAPE_OFFER_AFTER_SECONDS
from wake_alarm._escape_flow import (
    ALARM_ESCAPE_POLICY,
    EscapeCallbacks,
    EscapeDialog,
    build_tracker,
    is_offerable,
)

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


class TestPolicy:
    """The alarm's hatch is exactly as hard as sick mode."""

    def test_matches_sick_mode_defaults(self) -> None:
        """No softer budgets, no shorter wait, no shorter justification."""
        assert ALARM_ESCAPE_POLICY.budget_per_7_days == 1
        assert ALARM_ESCAPE_POLICY.budget_per_30_days == 3
        assert ALARM_ESCAPE_POLICY.budget_per_90_days == 10
        assert ALARM_ESCAPE_POLICY.lockout_seconds == 120
        assert ALARM_ESCAPE_POLICY.justification_min_chars == 120


class TestIsOfferable:
    """Two independent gates."""

    def test_hidden_early(self, tracker: EscapeTracker) -> None:
        """Reaching for it immediately is not allowed."""
        assert is_offerable(tracker, 5) is False

    def test_shown_after_the_threshold(self, tracker: EscapeTracker) -> None:
        """Once the alarm has been up a while, the hatch appears."""
        assert is_offerable(tracker, ESCAPE_OFFER_AFTER_SECONDS + 1) is True

    def test_hidden_when_budget_spent(self, tracker: EscapeTracker) -> None:
        """A spent budget removes it entirely, however long you wait."""
        tracker.history.used_days = [TODAY]
        with patch("gatelock._escape._today_iso", return_value=TODAY):
            assert is_offerable(tracker, 10_000) is False

    def test_build_tracker_loads(self, tmp_path: Path) -> None:
        """The real builder points at the config dir and loads cleanly."""
        with patch("wake_alarm._escape_flow.ESCAPE_HISTORY_FILE", tmp_path / "h.json"):
            assert build_tracker().history.used_days == []


class TestEscapeDialog:
    """The justification form."""

    def _dialog(
        self, tracker: EscapeTracker
    ) -> tuple[EscapeDialog, MagicMock, MagicMock]:
        granted, cancelled = MagicMock(), MagicMock()
        with patch("wake_alarm._escape_flow.tk") as fake_tk:
            # Distinct entries, or all three fields are one mock and a test
            # setting reason/onset/severity separately would only be setting
            # the last of them three times over.
            fake_tk.Entry.side_effect = lambda *_a, **_k: MagicMock()
            fake_tk.Text.return_value.get.return_value = "x" * 130
            dialog = EscapeDialog(
                MagicMock(),
                MagicMock(),
                tracker,
                EscapeCallbacks(on_granted=granted, on_cancel=cancelled),
            )
        return dialog, granted, cancelled

    def test_rejects_a_lazy_justification(self, tracker: EscapeTracker) -> None:
        """A short description is refused and nothing is recorded."""
        dialog, granted, _cancel = self._dialog(tracker)
        dialog._fields.description.get.return_value = "too short"
        dialog._fields.reason.get.return_value = "tired"
        dialog._fields.onset.get.return_value = "now"
        dialog._fields.severity.get.return_value = "5"

        dialog.submit()

        granted.assert_not_called()
        assert tracker.history.used_days == []

    def test_non_numeric_severity_is_refused(self, tracker: EscapeTracker) -> None:
        """A non-numeric severity becomes 0, which fails validation."""
        dialog, granted, _cancel = self._dialog(tracker)
        dialog._fields.description.get.return_value = "x" * 130
        dialog._fields.reason.get.return_value = "flu"
        dialog._fields.onset.get.return_value = "03:00"
        dialog._fields.severity.get.return_value = "very"

        dialog.submit()

        granted.assert_not_called()

    def test_accepts_and_starts_the_wait(self, tracker: EscapeTracker) -> None:
        """A proper justification is recorded and starts the countdown."""
        dialog, granted, _cancel = self._dialog(tracker)
        dialog._fields.description.get.return_value = "x" * 130
        dialog._fields.reason.get.return_value = "migraine"
        dialog._fields.onset.get.return_value = "03:00"
        dialog._fields.severity.get.return_value = "8"

        dialog.submit()

        assert len(tracker.history.used_days) == 1
        assert dialog._remaining >= 0
        granted.assert_not_called()  # only after the wait

    def test_refuses_when_budget_spent_mid_form(self, tracker: EscapeTracker) -> None:
        """The budget is re-checked at submit, not just when the form opened."""
        dialog, granted, _cancel = self._dialog(tracker)
        dialog._fields.description.get.return_value = "x" * 130
        dialog._fields.reason.get.return_value = "flu"
        dialog._fields.onset.get.return_value = "03:00"
        dialog._fields.severity.get.return_value = "8"
        tracker.history.used_days = [TODAY]

        with patch("gatelock._escape._today_iso", return_value=TODAY):
            dialog.submit()

        granted.assert_not_called()

    def test_tick_counts_down_then_grants(self, tracker: EscapeTracker) -> None:
        """The wait elapses exactly once, then the alarm is released."""
        dialog, granted, _cancel = self._dialog(tracker)
        dialog._remaining = 0

        dialog._tick()

        granted.assert_called_once_with()

    def test_tick_reschedules_while_waiting(self, tracker: EscapeTracker) -> None:
        """A remaining wait re-arms itself instead of granting."""
        dialog, granted, _cancel = self._dialog(tracker)
        dialog._remaining = 3

        dialog._tick()

        granted.assert_not_called()
        dialog.frame.after.assert_called_once()
