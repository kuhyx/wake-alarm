"""Tests for the derived correlation id."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from wake_alarm import _correlation
from wake_alarm._correlation import correlation_id, correlation_id_for
from wake_alarm._sync import Alarm

if TYPE_CHECKING:
    import pytest


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


def test_today_id_comes_from_the_alarm_not_the_start_instant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A late start must not shift the id away from the phone's.

    The alarm can begin a full catch-up window late, or hours late on a
    re-fire. Both halves derive the id independently with no handshake, so
    deriving the PC's from *now* rather than from the resolved alarm time
    would silently stop the two log streams joining.
    """
    monkeypatch.setattr(_correlation, "get_alarm", lambda: Alarm(6, 45, "remote"))
    today = datetime.now().astimezone()

    # Started at 07:35 -- 50 minutes into the catch-up window.
    assert _correlation.correlation_id_for_today() == correlation_id_for(
        6, 45, now=today
    )
    assert _correlation.correlation_id_for_today().endswith("-0645")
