"""Tue/Wed/Thu miss -> tomorrow's penalty file."""

from __future__ import annotations

from datetime import date, datetime
import json
from pathlib import Path
from unittest.mock import patch

from wake_alarm import _workday_penalty
from wake_alarm._workday_penalty import (
    is_stick_day,
    is_workday_miss,
    maybe_apply,
    penalty_entry,
    write_penalty,
)

# 2026-09-22 is a Tuesday.
TUESDAY = date(2026, 9, 22)
WEDNESDAY = date(2026, 9, 23)
THURSDAY = date(2026, 9, 24)
MONDAY = date(2026, 9, 21)
FRIDAY = date(2026, 9, 25)
SATURDAY = date(2026, 9, 26)
SUNDAY = date(2026, 9, 27)


class TestIsStickDay:
    def test_tuesday_wednesday_thursday_are_stick_days(self) -> None:
        assert is_stick_day(TUESDAY)
        assert is_stick_day(WEDNESDAY)
        assert is_stick_day(THURSDAY)

    def test_the_rest_of_the_week_is_not(self) -> None:
        for day in (MONDAY, FRIDAY, SATURDAY, SUNDAY):
            assert not is_stick_day(day)


class TestIsWorkdayMiss:
    def test_failed_is_always_a_miss(self) -> None:
        now = datetime(2026, 9, 22, 12, 0).astimezone()
        assert is_workday_miss({"outcome": "failed"}, now)

    def test_none_before_its_own_grace_is_not_a_miss_yet(self) -> None:
        now = datetime(2026, 9, 22, 8, 0).astimezone()
        entry = {
            "outcome": "none",
            "exempt_until": datetime(2026, 9, 22, 8, 15).astimezone().isoformat(),
        }
        assert not is_workday_miss(entry, now)

    def test_none_past_its_own_grace_is_a_miss(self) -> None:
        now = datetime(2026, 9, 22, 8, 16).astimezone()
        entry = {
            "outcome": "none",
            "exempt_until": datetime(2026, 9, 22, 8, 15).astimezone().isoformat(),
        }
        assert is_workday_miss(entry, now)

    def test_none_without_exempt_until_is_not_a_miss(self) -> None:
        now = datetime(2026, 9, 22, 12, 0).astimezone()
        assert not is_workday_miss({"outcome": "none"}, now)

    def test_none_with_unreadable_exempt_until_is_not_a_miss(self) -> None:
        now = datetime(2026, 9, 22, 12, 0).astimezone()
        entry = {"outcome": "none", "exempt_until": "not-a-timestamp"}
        assert not is_workday_miss(entry, now)

    def test_late_completed_is_not_a_miss(self) -> None:
        """The walk happened, just after the carrot's cutoff -- not a skip."""
        now = datetime(2026, 9, 22, 12, 0).astimezone()
        assert not is_workday_miss({"outcome": "completed"}, now)

    def test_in_progress_is_not_a_miss(self) -> None:
        now = datetime(2026, 9, 22, 8, 5).astimezone()
        assert not is_workday_miss({"outcome": "in_progress"}, now)


class TestPenaltyEntry:
    def test_penalty_targets_tomorrow(self) -> None:
        entry = penalty_entry(today=TUESDAY)
        assert entry == {
            "penalty_date": "2026-09-23",
            "issued_date": "2026-09-22",
        }


class TestWritePenalty:
    def test_round_trip_is_signed(self) -> None:
        entry = penalty_entry(today=TUESDAY)
        assert write_penalty(entry)
        assert "hmac" in entry
        on_disk = json.loads(_workday_penalty.WORKDAY_PENALTY_FILE.read_text())
        assert on_disk == entry

    def test_unsigned_when_the_key_is_missing(self) -> None:
        with patch("wake_alarm._workday_penalty.compute_entry_hmac", return_value=None):
            entry = penalty_entry(today=TUESDAY)
            assert write_penalty(entry)
        assert "hmac" not in entry

    def test_write_failure_is_false(self) -> None:
        with patch.object(Path, "write_text", side_effect=OSError("ro")):
            assert not write_penalty(penalty_entry(today=TUESDAY))


class TestMaybeApply:
    def _entry(self, outcome: str = "failed") -> dict[str, object]:
        return {"outcome": outcome}

    def test_weekend_never_gets_a_penalty(self) -> None:
        now = datetime(2026, 9, 26, 12, 0).astimezone()  # Saturday
        assert not maybe_apply(self._entry(), now)
        assert not _workday_penalty.WORKDAY_PENALTY_FILE.exists()

    def test_free_day_never_gets_a_penalty(self) -> None:
        now = datetime(2026, 9, 22, 12, 0).astimezone()  # Tuesday
        with patch(
            "wake_alarm._workday_penalty.freedays.is_free_day", return_value=True
        ):
            assert not maybe_apply(self._entry(), now)
        assert not _workday_penalty.WORKDAY_PENALTY_FILE.exists()

    def test_a_completed_stick_day_gets_no_penalty(self) -> None:
        now = datetime(2026, 9, 22, 12, 0).astimezone()  # Tuesday
        with patch(
            "wake_alarm._workday_penalty.freedays.is_free_day", return_value=False
        ):
            assert not maybe_apply(self._entry("completed"), now)
        assert not _workday_penalty.WORKDAY_PENALTY_FILE.exists()

    def test_a_missed_stick_day_writes_tomorrows_penalty(self) -> None:
        now = datetime(2026, 9, 22, 12, 0).astimezone()  # Tuesday
        with patch(
            "wake_alarm._workday_penalty.freedays.is_free_day", return_value=False
        ):
            assert maybe_apply(self._entry("failed"), now)
        on_disk = json.loads(_workday_penalty.WORKDAY_PENALTY_FILE.read_text())
        assert on_disk["penalty_date"] == "2026-09-23"
