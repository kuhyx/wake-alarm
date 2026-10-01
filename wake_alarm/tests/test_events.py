"""Named events and the change-only state behind them."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

from wake_alarm import _events
from wake_alarm._events import emit, emit_on_change, last_value, remember

if TYPE_CHECKING:
    import pytest


def _records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if hasattr(r, "event")]


def test_emit_carries_event_and_fields(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        emit("rtc_armed", "wake at 06:50", epoch=5)
    (record,) = _records(caplog)
    assert record.event == "rtc_armed"
    assert record.fields == {"epoch": 5}
    assert "rtc_armed: wake at 06:50" in record.getMessage()


def test_emit_on_change_logs_once_per_key(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        assert emit_on_change("fallback_tick", "a", "first")
        assert not emit_on_change("fallback_tick", "a", "again")
        assert emit_on_change("fallback_tick", "b", "changed")
    assert [r.getMessage() for r in _records(caplog)] == [
        "fallback_tick: first",
        "fallback_tick: changed",
    ]
    assert last_value("fallback_tick") == "b"


def test_remember_and_forget() -> None:
    remember("slot", "x")
    remember("slot", "x")  # unchanged: no rewrite needed
    assert last_value("slot") == "x"
    remember("slot", None)
    assert last_value("slot") is None
    remember("slot", None)  # forgetting nothing is a no-op
    assert not _events.EVENT_STATE_FILE.read_text().count("slot")


def test_unreadable_or_odd_state_reads_empty() -> None:
    _events.EVENT_STATE_FILE.write_text("{nope")
    assert last_value("slot") is None
    _events.EVENT_STATE_FILE.write_text("[1, 2]")
    assert last_value("slot") is None
    _events.EVENT_STATE_FILE.write_text(json.dumps({"a": "x", "b": 3}))
    assert last_value("a") == "x"
    assert last_value("b") is None


def test_write_failure_only_costs_a_repeat(caplog: pytest.LogCaptureFixture) -> None:
    with (
        patch.object(Path, "write_text", side_effect=OSError("ro")),
        caplog.at_level(logging.INFO),
    ):
        remember("slot", "x")
    assert last_value("slot") is None
    assert "Cannot persist" in caplog.text
