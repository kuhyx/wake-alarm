"""Tests for the daily ramp — and that its three copies agree."""

from __future__ import annotations

from datetime import date
from pathlib import Path
import re

import pytest

from wake_alarm._ramp import (
    RAMP_ANCHOR,
    RAMP_FLOOR_MINUTES,
    RAMP_START_MINUTES,
    baseline_minutes,
    baseline_time,
    local_today,
)

_PHONE = Path(__file__).resolve().parents[2] / "phone_app"
_DART = _PHONE / "lib/services/alarm_ramp.dart"
_KOTLIN = _PHONE / "android/app/src/main/kotlin/com/kuhy/wake_alarm_sync/AlarmRamp.kt"


class TestBaseline:
    """A minute earlier per calendar day, from 08:00 to a permanent 07:00."""

    @pytest.mark.parametrize(
        ("day", "expected"),
        [
            (date(2026, 1, 1), (8, 0)),
            (date(2026, 9, 25), (8, 0)),
            (date(2026, 9, 26), (7, 59)),
            (date(2026, 10, 24), (7, 31)),
            (date(2026, 10, 25), (7, 30)),
            (date(2026, 10, 26), (7, 29)),
            (date(2026, 11, 23), (7, 1)),
            (date(2026, 11, 24), (7, 0)),
            (date(2026, 11, 25), (7, 0)),
            (date(2030, 6, 1), (7, 0)),
        ],
    )
    def test_the_ramp(self, day: date, expected: tuple[int, int]) -> None:
        """Before the anchor stays 08:00; the floor holds for good."""
        assert baseline_time(day) == expected

    def test_never_moves_later(self) -> None:
        """Day over day, the baseline is monotonically non-increasing."""
        days = [date.fromordinal(RAMP_ANCHOR.toordinal() + n) for n in range(-5, 90)]
        minutes = [baseline_minutes(d) for d in days]
        assert minutes == sorted(minutes, reverse=True)

    def test_local_today_is_a_date(self) -> None:
        """The seam returns the system-local calendar date."""
        assert isinstance(local_today(), date)


def _grab(pattern: str, text: str) -> tuple[str, ...]:
    match = re.search(pattern, text)
    assert match is not None, pattern
    return match.groups()


class TestCopiesAgree:
    """The Dart and Kotlin copies carry the same constants as this one.

    Three copies of a pure function are cheap; three copies that silently
    disagree mean the phone rings at one time and the PC fires at another.
    """

    def test_dart(self) -> None:
        """``alarm_ramp.dart`` matches ``_ramp.py``."""
        text = _DART.read_text()
        y, m, d = _grab(r"rampAnchor = DateTime\.utc\((\d+), (\d+), (\d+)\)", text)
        assert date(int(y), int(m), int(d)) == RAMP_ANCHOR
        h, mi = _grab(r"rampStartMinutes = (\d+) \* (\d+);", text)
        assert int(h) * int(mi) == RAMP_START_MINUTES
        h, mi = _grab(r"rampFloorMinutes = (\d+) \* (\d+);", text)
        assert int(h) * int(mi) == RAMP_FLOOR_MINUTES

    def test_kotlin(self) -> None:
        """``AlarmRamp.kt`` matches ``_ramp.py``."""
        text = _KOTLIN.read_text()
        y, m, d = _grab(
            r"ANCHOR: LocalDate = LocalDate\.of\((\d+), (\d+), (\d+)\)", text
        )
        assert date(int(y), int(m), int(d)) == RAMP_ANCHOR
        h, mi = _grab(r"START_MINUTES = (\d+) \* (\d+)", text)
        assert int(h) * int(mi) == RAMP_START_MINUTES
        h, mi = _grab(r"FLOOR_MINUTES = (\d+) \* (\d+)", text)
        assert int(h) * int(mi) == RAMP_FLOOR_MINUTES
