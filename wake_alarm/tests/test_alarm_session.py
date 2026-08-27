"""Tests for the fire-time session record that survives a hard power-off."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from typing import TYPE_CHECKING

import pytest

from wake_alarm import _alarm_session
from wake_alarm._alarm_session import (
    STATE_FINISHED,
    STATE_RINGING,
    finish_session,
    load_session,
    should_refire,
    start_session,
    unfinished_session_age,
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def session_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the record at a temporary file, never the real one."""
    path = tmp_path / "alarm_session.json"
    monkeypatch.setattr(_alarm_session, "ALARM_SESSION_FILE", path)
    return path


class TestStartSession:
    """Opening a record the moment the alarm starts ringing."""

    def test_writes_a_signed_ringing_record(self, session_file: Path) -> None:
        """The record exists before anything can go wrong."""
        assert start_session("wake-20260827-0700") is True
        entry = json.loads(session_file.read_text())
        assert entry["state"] == STATE_RINGING
        assert entry["correlation"] == "wake-20260827-0700"
        assert "hmac" in entry
        # An aware timestamp: freshness is measured as elapsed time, so the
        # offset has to be carried rather than assumed.
        assert datetime.fromisoformat(str(entry["fired_at"])).tzinfo is not None

    def test_creates_the_parent_directory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A fresh install has no ~/.config/wake_alarm yet."""
        monkeypatch.setattr(
            _alarm_session, "ALARM_SESSION_FILE", tmp_path / "new" / "s.json"
        )
        assert start_session("wake-20260827-0700") is True

    def test_unwritable_path_is_survivable(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A failed write must never stop the alarm from ringing."""
        blocker = tmp_path / "blocker"
        blocker.write_text("not a directory")
        monkeypatch.setattr(_alarm_session, "ALARM_SESSION_FILE", blocker / "s.json")
        with caplog.at_level("WARNING"):
            assert start_session("wake-20260827-0700") is False
        assert "Failed to write" in caplog.text

    def test_saves_unsigned_when_no_hmac_key(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """An unsigned record still beats no record at all."""
        monkeypatch.setattr(_alarm_session, "compute_entry_hmac", lambda _entry: None)
        with caplog.at_level("WARNING"):
            assert start_session("wake-20260827-0700") is True
        assert "unsigned alarm session" in caplog.text


class TestFinishSession:
    """Closing the record however the alarm actually ended."""

    def test_marks_the_record_finished(self, session_file: Path) -> None:
        """Dismissal, escape hatch and SIGTERM all land here."""
        start_session("wake-20260827-0700")
        assert finish_session() is True
        entry = json.loads(session_file.read_text())
        assert entry["state"] == STATE_FINISHED
        # fired_at is preserved: it is the audit trail of when it rang.
        assert entry["fired_at"] is not None
        assert entry["correlation"] == "wake-20260827-0700"

    def test_no_record_to_finish(self) -> None:
        """on_close() runs even when no session was ever opened."""
        assert finish_session() is False


class TestLoadSession:
    """Reading the record back, rejecting anything untrustworthy."""

    def test_absent_file(self) -> None:
        """No record is not an error."""
        assert load_session() is None

    def test_unreadable_json(
        self, session_file: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A truncated write is treated as no record."""
        session_file.write_text("{not json")
        with caplog.at_level("WARNING"):
            assert load_session() is None
        assert "Cannot read" in caplog.text

    def test_non_dict_payload(self, session_file: Path) -> None:
        """A JSON list is not a record."""
        session_file.write_text("[1, 2, 3]")
        assert load_session() is None

    def test_tampered_record_is_rejected(
        self, session_file: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Hand-editing state must not be able to fake -- or force -- a ring."""
        start_session("wake-20260827-0700")
        entry = json.loads(session_file.read_text())
        entry["state"] = STATE_FINISHED
        session_file.write_text(json.dumps(entry))
        with caplog.at_level("WARNING"):
            assert load_session() is None
        assert "HMAC verification failed" in caplog.text


class TestShouldRefire:
    """The decision _trigger acts on."""

    def test_no_record_does_not_refire(self) -> None:
        """The ordinary case: nothing was cut short."""
        assert should_refire() is False

    def test_ringing_record_refires(self) -> None:
        """The whole point: a power-off mid-alarm rings again."""
        start_session("wake-20260827-0700")
        assert should_refire() is True

    def test_finished_record_does_not_refire(self) -> None:
        """A dismissed alarm stays dismissed."""
        start_session("wake-20260827-0700")
        finish_session()
        assert should_refire() is False

    def test_stale_record_does_not_refire(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Bounded on purpose.

        An alarm that died before dismissal leaves a record nothing will ever
        clear; unbounded, this would restart the alarm every minute forever.
        """
        start_session("wake-20260827-0700")
        much_later = datetime.now(tz=timezone.utc).astimezone() + timedelta(days=1)
        with caplog.at_level("INFO"):
            assert should_refire(now=much_later) is False
        assert "Ignoring an unfinished alarm session" in caplog.text

    def test_a_backward_clock_jump_still_refires(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Fails *closed*, which is the whole point of the record.

        NTP correcting after a resume moves the clock backwards, leaving the
        record stamped in the future. Discarding it there would mean: alarm
        fires on a fast clock, clock is corrected, and the power-off escape
        quietly works again -- on a machine that hibernates nightly, i.e. the
        exact scenario this record exists to close.
        """
        start_session("wake-20260827-0700")
        corrected = datetime.now(tz=timezone.utc).astimezone() - timedelta(minutes=5)
        with caplog.at_level("INFO"):
            assert should_refire(now=corrected) is True
        assert "in the future" in caplog.text

    def test_a_wildly_future_record_is_ignored(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Bounded, so a broken RTC cannot create an endless re-fire."""
        start_session("wake-20260827-0700")
        way_earlier = datetime.now(tz=timezone.utc).astimezone() - timedelta(hours=6)
        with caplog.at_level("WARNING"):
            assert should_refire(now=way_earlier) is False
        assert "beyond the" in caplog.text

    def test_missing_timestamp_is_ignored(
        self,
        session_file: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A record with no usable fired_at cannot be aged, so it is dropped."""
        monkeypatch.setattr(_alarm_session, "verify_entry_hmac", lambda _e: True)
        session_file.write_text(json.dumps({"state": STATE_RINGING}))
        with caplog.at_level("WARNING"):
            assert unfinished_session_age() is None
        assert "no usable fired_at" in caplog.text

    @pytest.mark.parametrize(
        "fired_at",
        [
            "not-a-timestamp",
            # Naive: without an offset the elapsed-time comparison is
            # meaningless, which is exactly the ambiguity this record avoids.
            "2026-08-27T07:00:00",
        ],
    )
    def test_unusable_timestamps_are_ignored(
        self, session_file: Path, monkeypatch: pytest.MonkeyPatch, fired_at: str
    ) -> None:
        """Neither an unparsable nor a naive timestamp can drive a re-fire."""
        monkeypatch.setattr(_alarm_session, "verify_entry_hmac", lambda _e: True)
        session_file.write_text(
            json.dumps({"state": STATE_RINGING, "fired_at": fired_at})
        )
        assert should_refire() is False

    def test_age_is_reported_for_a_live_session(self) -> None:
        """The age helper is what makes the bound observable."""
        start_session("wake-20260827-0700")
        later = datetime.now(tz=timezone.utc).astimezone() + timedelta(seconds=90)
        age = unfinished_session_age(now=later)
        assert age is not None
        assert 89 <= age <= 92
