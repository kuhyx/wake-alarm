"""Tests for the derived correlation id."""

from __future__ import annotations

from datetime import datetime

from wake_alarm._correlation import correlation_id, correlation_id_for


def _local(year: int, month: int, day: int, hour: int, minute: int) -> datetime:
    """Build an aware local datetime, matching the idiom in test_trigger.py."""
    return datetime(year, month, day, hour, minute, tzinfo=None).astimezone()


def test_correlation_id_formats_local_instant() -> None:
    """The id encodes the local date and the alarm's wall-clock time."""
    assert correlation_id(_local(2026, 8, 26, 7, 0)) == "wake-20260826-0700"


def test_correlation_id_pads_single_digits() -> None:
    """Single-digit months, days, hours and minutes are zero padded."""
    assert correlation_id(_local(2026, 1, 2, 3, 4)) == "wake-20260102-0304"


def test_correlation_id_is_stable_for_the_same_instant() -> None:
    """Two independent computations agree, which is the whole point."""
    moment = _local(2026, 12, 31, 23, 59)
    assert correlation_id(moment) == correlation_id(moment)


def test_correlation_id_for_uses_the_date_of_now() -> None:
    """The (hour, minute) form takes its date from the supplied instant."""
    assert (
        correlation_id_for(7, 30, now=_local(2026, 8, 26, 22, 15))
        == "wake-20260826-0730"
    )


def test_correlation_id_for_ignores_the_time_of_now() -> None:
    """Only *now*'s date matters; its own time is replaced."""
    early = correlation_id_for(6, 0, now=_local(2026, 8, 26, 1, 2))
    late = correlation_id_for(6, 0, now=_local(2026, 8, 26, 23, 58))
    assert early == late == "wake-20260826-0600"
