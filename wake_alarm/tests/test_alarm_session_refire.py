"""Tests for the re-fire decision driven by the session record.

Split from ``test_alarm_session.py`` for the 250-line cap. The header is copied
whole: without the autouse ``session_file`` fixture these tests would read and
write the *production* record, which the next real trigger tick would act on.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from typing import TYPE_CHECKING

import pytest

from wake_alarm import _alarm_session
from wake_alarm._alarm_session import (
    STATE_RINGING,
    finish_session,
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
        much_later = datetime.now(tz=UTC).astimezone() + timedelta(days=1)
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
        corrected = datetime.now(tz=UTC).astimezone() - timedelta(minutes=5)
        with caplog.at_level("INFO"):
            assert should_refire(now=corrected) is True
        assert "in the future" in caplog.text

    def test_a_wildly_future_record_is_ignored(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Bounded, so a broken RTC cannot create an endless re-fire."""
        start_session("wake-20260827-0700")
        way_earlier = datetime.now(tz=UTC).astimezone() - timedelta(hours=6)
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
        later = datetime.now(tz=UTC).astimezone() + timedelta(seconds=90)
        age = unfinished_session_age(now=later)
        assert age is not None
        assert 89 <= age <= 92
