"""``refresh`` retries an unreadable backend; ``next_step`` is signed."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
import json
import logging
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from wake_alarm import _session
from wake_alarm._constants import REFRESH_POLL_SECONDS, REFRESH_RETRY_SECONDS
from wake_alarm._session import read_entry, refresh, to_entry, write_entry
from wake_alarm._session_payload import SessionRecord
from wake_alarm._sync import Alarm

if TYPE_CHECKING:
    from wake_alarm.tests.conftest import FakeClock

NOW = datetime(2026, 9, 19, 8, 30).astimezone()
TODAY = "2026-09-19"


def _live(passed: tuple[str, ...] = ("bathroomIn",)) -> SessionRecord:
    return SessionRecord(
        date=TODAY,
        outcome="in_progress",
        started_at="2026-09-19T08:01:00.000",
        finished_at=None,
        energy=3,
        weight_kg=73.8,
        re_rings=0,
        device_id="p",
        published_at=1.0,
        passed_legs=passed,
    )


@pytest.fixture(autouse=True)
def _alarm() -> object:
    with patch("wake_alarm._session.get_alarm", return_value=Alarm(8, 0, "cache")):
        yield


class TestRefreshRetry:
    """2026-11-07: booted without DNS; one try, then a 2-minute gap."""

    def test_unreadable_backend_leaves_the_file_alone(
        self, fake_clock: FakeClock
    ) -> None:
        write_entry(to_entry(_live(), today=TODAY, refreshed_at=5.0))
        with patch("wake_alarm._session.fetch_firebase_logs", return_value=None):
            assert refresh(NOW, sleep=fake_clock.sleep, clock=fake_clock.now) is None
        assert read_entry() is not None

    def test_a_backend_that_recovers_is_retried_into_todays_entry(
        self, fake_clock: FakeClock
    ) -> None:
        with patch(
            "wake_alarm._session.fetch_firebase_logs", side_effect=[None, None, []]
        ) as fetch:
            entry = refresh(NOW, sleep=fake_clock.sleep, clock=fake_clock.now)
        assert entry is not None
        assert (entry["date"], entry["outcome"]) == (TODAY, "none")
        assert read_entry() == entry
        assert fetch.call_count == 3
        assert fake_clock.sleeps == [REFRESH_POLL_SECONDS, REFRESH_POLL_SECONDS]

    def test_a_dead_backend_gives_up_after_the_budget_and_says_so(
        self, caplog: pytest.LogCaptureFixture, fake_clock: FakeClock
    ) -> None:
        with (
            patch("wake_alarm._session.fetch_firebase_logs", return_value=None),
            caplog.at_level(logging.WARNING),
        ):
            assert refresh(NOW, sleep=fake_clock.sleep, clock=fake_clock.now) is None
        assert fake_clock.sleeps == [REFRESH_POLL_SECONDS] * (
            REFRESH_RETRY_SECONDS // REFRESH_POLL_SECONDS
        )
        warnings = [r.getMessage() for r in caplog.records if r.levelno >= 30]
        assert any(f"{REFRESH_RETRY_SECONDS} s" in w for w in warnings)

    def test_sick_day_cancel_runs_once_before_the_loop(
        self, fake_clock: FakeClock
    ) -> None:
        with (
            patch("wake_alarm._session.fetch_firebase_logs", return_value=None),
            patch("wake_alarm._session._cancel_for_sick_day") as cancel,
        ):
            refresh(NOW, sleep=fake_clock.sleep, clock=fake_clock.now)
        cancel.assert_called_once()


class TestNextStep:
    """The entry names the next leg and signs it."""

    def test_in_progress_entry_names_the_next_leg(self) -> None:
        entry = to_entry(_live(), today=TODAY, refreshed_at=5.0)
        assert entry["next_step"] == "Shower, then tap the bathroom tag again"

    def test_next_step_is_null_unless_the_morning_is_live(self) -> None:
        done = replace(_live(), outcome="completed", finished_at="2026-09-19T08:40")
        assert to_entry(done, today=TODAY, refreshed_at=5.0)["next_step"] is None
        failed = replace(_live(), outcome="failed")
        assert to_entry(failed, today=TODAY, refreshed_at=5.0)["next_step"] is None
        assert to_entry(None, today=TODAY, refreshed_at=5.0)["next_step"] is None

    def test_tampering_next_step_breaks_verification(self) -> None:
        write_entry(to_entry(_live(), today=TODAY, refreshed_at=5.0))
        assert read_entry() is not None
        path = _session.MORNING_SESSION_FILE
        tampered = json.loads(path.read_text())
        tampered["next_step"] = None
        path.write_text(json.dumps(tampered))
        assert read_entry() is None
