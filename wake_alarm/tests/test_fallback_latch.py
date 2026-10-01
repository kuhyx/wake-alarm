"""The fallback ring's per-day latch file."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from unittest.mock import patch

from wake_alarm import _fallback_latch
from wake_alarm._fallback_latch import (
    Latch,
    mark_started,
    mark_stopped,
    read_latch,
    write_latch,
)

DAY = "2026-10-01"
NOW = datetime(2026, 10, 1, 7, 2).astimezone()


def test_absent_latch_is_none() -> None:
    assert read_latch(DAY) is None


def test_unreadable_or_other_days_latch_is_none() -> None:
    _fallback_latch.FALLBACK_RING_FILE.write_text("{nope")
    assert read_latch(DAY) is None
    _fallback_latch.FALLBACK_RING_FILE.write_text(json.dumps({"date": "2026-09-30"}))
    assert read_latch(DAY) is None
    _fallback_latch.FALLBACK_RING_FILE.write_text("[]")
    assert read_latch(DAY) is None


def test_start_then_stop_round_trips_the_contract_shape() -> None:
    latch = mark_started(None, day=DAY, now=NOW, reason="phone_silent")
    assert read_latch(DAY) == latch
    assert latch.started() == NOW
    stopped = mark_stopped(latch, now=NOW, stop_reason="cap")
    on_disk = json.loads(_fallback_latch.FALLBACK_RING_FILE.read_text())
    assert set(on_disk) == {"date", "started_at", "stopped_at", "reason", "stop_reason"}
    assert read_latch(DAY) == stopped
    assert stopped.stop_reason == "cap"


def test_a_resumed_ring_keeps_its_first_start() -> None:
    first = mark_started(None, day=DAY, now=NOW, reason="phone_silent")
    died = mark_stopped(first, now=NOW, stop_reason="terminated")
    later = datetime(2026, 10, 1, 7, 20).astimezone()
    resumed = mark_started(died, day=DAY, now=later, reason="no_session")
    assert resumed.started_at == first.started_at
    assert resumed.reason == "phone_silent"
    assert resumed.stopped_at is None
    assert resumed.stop_reason is None


def test_a_latch_without_a_start_starts_fresh() -> None:
    latch = mark_started(Latch(date=DAY), day=DAY, now=NOW, reason="no_session")
    assert latch.started_at == NOW.isoformat()
    assert Latch(date=DAY).started() is None


def test_write_failure_is_false() -> None:
    with patch.object(Path, "write_text", side_effect=OSError("ro")):
        assert not write_latch(Latch(date=DAY))


def test_garbage_fields_read_as_none() -> None:
    _fallback_latch.FALLBACK_RING_FILE.write_text(
        json.dumps({"date": DAY, "started_at": None, "stopped_at": 5, "reason": ""})
    )
    assert read_latch(DAY) == Latch(date=DAY)
