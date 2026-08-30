"""Tests for _state.py's read-side queries — the workout skip, and the two
'already done today' gates the trigger consults.

Split out of test_state.py for the 250-line gate; that file keeps the
UTC day key and the save/load round-trip."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from wake_alarm._state import (
    _today_str,
    was_trigger_fired_today,
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def wake_state_file(tmp_path: Path) -> Path:
    """Provide a temporary wake state file path."""
    return tmp_path / "wake_state.json"


@pytest.fixture(autouse=True)
def _patch_wake_state_file(wake_state_file: Path) -> None:
    """Redirect WAKE_STATE_FILE to tmp_path for all tests."""
    with patch(
        "wake_alarm._state.WAKE_STATE_FILE",
        wake_state_file,
    ):
        yield


class TestWasTriggerFiredToday:
    """Tests for the trigger's once-per-day latch."""

    def test_returns_false_when_no_state(self) -> None:
        """Return False when no state file exists."""
        assert was_trigger_fired_today() is False

    def test_returns_true_once_fired(
        self,
        wake_state_file: Path,
    ) -> None:
        """Return True when the routine already started today."""
        state = {
            "date": _today_str(),
            "fired_at": "07:04",
            "hmac": "sig",
        }
        wake_state_file.write_text(json.dumps(state))
        with patch(
            "wake_alarm._state.verify_entry_hmac",
            return_value=True,
        ):
            assert was_trigger_fired_today() is True

    def test_returns_false_before_firing(
        self,
        wake_state_file: Path,
    ) -> None:
        """Return False when it has not started yet."""
        state = {
            "date": _today_str(),
            "fired_at": None,
            "hmac": "sig",
        }
        wake_state_file.write_text(json.dumps(state))
        with patch(
            "wake_alarm._state.verify_entry_hmac",
            return_value=True,
        ):
            assert was_trigger_fired_today() is False
