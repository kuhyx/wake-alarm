"""Gathering the fallback's facts, and the bookkeeping they trigger."""

from __future__ import annotations

from datetime import datetime
import json
import logging
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from wake_alarm import _fallback_observe
from wake_alarm._events import last_value, remember
from wake_alarm._fallback_latch import Latch, mark_started, mark_stopped
from wake_alarm._fallback_observe import (
    SETTLED_SLOT,
    observe,
    record,
    remember_final,
    settled_reason,
)
from wake_alarm._sync import Alarm

if TYPE_CHECKING:
    from collections.abc import Generator

DAY = "2026-10-01"
NOW = datetime(2026, 10, 1, 7, 10).astimezone()
REASON = "the phone was in a drawer charging and never rang this morning"


def _log(**fields: object) -> str:
    return json.dumps({"alarm": {"fields": {k: [v, "h"] for k, v in fields.items()}}})


@pytest.fixture(autouse=True)
def _alarm() -> Generator[None]:
    with patch.object(
        _fallback_observe, "get_alarm", return_value=Alarm(7, 0, "cache")
    ):
        yield


def test_outside_the_window_never_fetches() -> None:
    fetch = MagicMock()
    with patch.object(_fallback_observe, "fetch_firebase_logs", fetch):
        seen = observe(datetime(2026, 10, 1, 5, 0).astimezone(), sync=True)
    fetch.assert_not_called()
    assert seen.reachable
    assert seen.view is None


def test_a_free_day_never_fetches() -> None:
    fetch = MagicMock()
    with (
        patch.object(_fallback_observe, "fetch_firebase_logs", fetch),
        patch.object(_fallback_observe.freedays, "is_free_day", return_value=True),
    ):
        assert observe(NOW, sync=False).facts.free_day
    fetch.assert_not_called()


def test_unreachable_firebase_is_no_ping_no_session() -> None:
    with patch.object(_fallback_observe, "fetch_firebase_logs", return_value=None):
        seen = observe(NOW, sync=False)
    assert not seen.reachable
    facts = seen.facts
    assert not (facts.escaped)
    assert not (facts.session_started)
    assert not (facts.ring_started)


def test_facts_from_the_phone() -> None:
    session = {"date": DAY, "started_at": f"{DAY}T07:05:00", "outcome": "active"}
    raw = _log(
        current_session=session,
        ring_started={"date": DAY, "at": f"{DAY}T07:00:05"},
        escapes=[{"id": "e", "date": DAY, "at": "x", "reason": REASON}],
    )
    with patch.object(
        _fallback_observe, "fetch_firebase_logs", return_value=[("p", raw)]
    ):
        seen = observe(NOW, sync=False)
    assert seen.facts.session_started
    assert seen.facts.ring_started
    assert seen.facts.escaped
    assert seen.view is not None


def test_yesterdays_session_does_not_count() -> None:
    session = {"date": "2026-09-30", "started_at": "x", "outcome": "completed"}
    with patch.object(
        _fallback_observe,
        "fetch_firebase_logs",
        return_value=[("p", _log(morning_sessions=[session]))],
    ):
        assert not observe(NOW, sync=False).facts.session_started


def test_settled_from_latch_or_event_state() -> None:
    assert settled_reason(DAY, None) is None
    latch = mark_stopped(
        mark_started(None, day=DAY, now=NOW, reason="phone_silent"),
        now=NOW,
        stop_reason="cap",
    )
    assert settled_reason(DAY, latch) == "cap"
    assert settled_reason(DAY, Latch(date=DAY, stop_reason="terminated")) is None
    remember_final(DAY, "waiting")
    assert last_value(SETTLED_SLOT) is None
    remember_final(DAY, "escape")
    assert settled_reason(DAY, None) == "escape"
    assert settled_reason("2026-10-02", None) is None
    remember(SETTLED_SLOT, f"{DAY}|")
    assert settled_reason(DAY, None) is None


def test_record_logs_unreachable_once_and_resets(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with (
        patch.object(_fallback_observe, "fetch_firebase_logs", return_value=None),
        caplog.at_level(logging.INFO),
    ):
        seen = observe(NOW, sync=False)
        record(seen)
        record(seen)
    assert caplog.text.count("firebase_unreachable:") == 1
    with patch.object(_fallback_observe, "fetch_firebase_logs", return_value=[]):
        record(observe(NOW, sync=False))
    assert last_value("firebase_unreachable") is None


def test_record_notes_escapes() -> None:
    raw = _log(escapes=[{"id": "e", "date": DAY, "at": "x", "reason": REASON}])
    with patch.object(
        _fallback_observe, "fetch_firebase_logs", return_value=[("p", raw)]
    ):
        record(observe(NOW, sync=False))
    assert last_value("escape_seen") == "e"
