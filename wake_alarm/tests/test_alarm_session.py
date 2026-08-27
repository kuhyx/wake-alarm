"""Tests for the fire-time session record that survives a hard power-off."""

from __future__ import annotations

from datetime import datetime
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

    def test_an_unsigned_record_is_honoured(
        self,
        session_file: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """No HMAC key must not silently disable the power-off defence.

        ``verify_entry_hmac`` returns False both for a forgery *and* for a
        machine with no key at all. Treating them alike meant that on such a
        machine every session record was unreadable and the re-fire simply did
        not happen -- found by running the vmbox harness, where /etc/gatelock
        is absent.
        """
        monkeypatch.setattr(_alarm_session, "compute_entry_hmac", lambda _e: None)
        start_session("wake-20260827-0700")
        assert "hmac" not in json.loads(session_file.read_text())
        with caplog.at_level("WARNING"):
            assert should_refire() is True
        assert "unsigned" in caplog.text

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
