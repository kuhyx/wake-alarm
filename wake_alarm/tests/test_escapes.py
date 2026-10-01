"""Escapes on the PC: escape_seen once, penalties cancelled, refresh wiring."""

from __future__ import annotations

from datetime import date, datetime
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

from wake_alarm import _session, _workday_penalty
from wake_alarm._enforcement_payload import EnforcementView
from wake_alarm._enforcement_records import Escape
from wake_alarm._escapes import note_escapes
from wake_alarm._events import last_value
from wake_alarm._sync import Alarm
from wake_alarm._workday_penalty import (
    cancel_for_escapes,
    issued_date,
    maybe_apply,
    penalty_entry,
    write_penalty,
)

if TYPE_CHECKING:
    import pytest

REASON = "the alarm never rang because the phone rebooted overnight"
TUESDAY = date(2026, 9, 22)
NOON = datetime(2026, 9, 22, 12, 0).astimezone()


def _escape(ident: str, day: str = "2026-09-22") -> Escape:
    return Escape(ident, day, f"{day}T08:00:00", REASON)


class TestNoteEscapes:
    def test_each_escape_is_logged_once(self, caplog: pytest.LogCaptureFixture) -> None:
        view = EnforcementView(escapes=(_escape("a"), _escape("b")))
        with caplog.at_level(logging.INFO):
            assert note_escapes(view) == ["a", "b"]
            assert note_escapes(view) == []
        assert caplog.text.count("escape_seen:") == 2
        assert last_value("escape_seen") == "a,b"

    def test_seen_ids_are_pruned_to_what_the_phone_carries(self) -> None:
        note_escapes(EnforcementView(escapes=(_escape("a"),)))
        note_escapes(EnforcementView(escapes=(_escape("b"),)))
        assert last_value("escape_seen") == "b"
        note_escapes(EnforcementView())
        assert last_value("escape_seen") is None

    def test_an_unhonoured_escape_is_ignored(self) -> None:
        short = Escape("s", "2026-09-22", "x", "too short")
        assert note_escapes(EnforcementView(escapes=(short,))) == []


class TestPenalty:
    def test_escaped_day_gets_no_penalty(self) -> None:
        with patch.object(_workday_penalty.freedays, "is_free_day", return_value=False):
            assert not maybe_apply(
                {"outcome": "failed"}, NOON, escaped_dates=frozenset({"2026-09-22"})
            )
        assert issued_date() is None

    def test_penalty_written_is_logged_once_per_day(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with (
            patch.object(_workday_penalty.freedays, "is_free_day", return_value=False),
            caplog.at_level(logging.INFO),
        ):
            assert maybe_apply({"outcome": "failed"}, NOON)
            assert maybe_apply({"outcome": "failed"}, NOON)
        assert caplog.text.count("penalty_written:") == 1

    def test_a_failed_write_logs_nothing(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with (
            patch.object(_workday_penalty.freedays, "is_free_day", return_value=False),
            patch.object(Path, "write_text", side_effect=OSError("ro")),
            caplog.at_level(logging.INFO),
        ):
            assert not maybe_apply({"outcome": "failed"}, NOON)
        assert "penalty_written" not in caplog.text

    def test_cancel_removes_only_the_escaped_days_penalty(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        assert not cancel_for_escapes(frozenset({"2026-09-22"}))  # nothing on disk
        write_penalty(penalty_entry(today=TUESDAY))
        assert not cancel_for_escapes(frozenset({"2026-09-23"}))
        with caplog.at_level(logging.INFO):
            assert cancel_for_escapes(frozenset({"2026-09-22"}))
        assert issued_date() is None
        assert "penalty_cancelled" in caplog.text

    def test_cancel_failure_is_false(self) -> None:
        write_penalty(penalty_entry(today=TUESDAY))
        with patch.object(Path, "unlink", side_effect=OSError("ro")):
            assert not cancel_for_escapes(frozenset({"2026-09-22"}))

    def test_issued_date_tolerates_garbage(self) -> None:
        _workday_penalty.WORKDAY_PENALTY_FILE.write_text("{bad")
        assert issued_date() is None
        _workday_penalty.WORKDAY_PENALTY_FILE.write_text(json.dumps([1]))
        assert issued_date() is None
        _workday_penalty.WORKDAY_PENALTY_FILE.write_text(json.dumps({"issued_date": 5}))
        assert issued_date() is None


def test_refresh_cancels_a_penalty_the_morning_after() -> None:
    """Escape for Thursday arrives Friday: Thursday's penalty goes."""
    write_penalty(penalty_entry(today=date(2026, 9, 24)))
    escape = {"id": "e", "date": "2026-09-24", "at": "x", "reason": REASON}
    raw = json.dumps({"alarm": {"fields": {"escapes": [[escape], "h"]}}})
    friday = datetime(2026, 9, 25, 9, 0).astimezone()
    with (
        patch.object(_session, "fetch_firebase_logs", return_value=[("p", raw)]),
        patch.object(_session, "get_alarm", return_value=Alarm(7, 0, "cache")),
    ):
        assert _session.refresh(friday) is not None
    assert issued_date() is None
