"""The Dart and Kotlin copies of the workdays agree with ``freedays.WORKDAYS``.

The phone code cannot import the Python package that owns the definition, so
it keeps literal copies; this is the check that keeps them honest.
"""

from __future__ import annotations

from pathlib import Path
import re

import freedays

_PHONE = Path(__file__).resolve().parents[2] / "phone_app"
_KOTLIN = _PHONE / "android/app/src/main/kotlin/com/kuhy/wake_alarm_sync"
_NAMES = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def _weekdays(block: str) -> frozenset[int]:
    """Map the weekday names written in *block* to Python weekday() numbers."""
    return frozenset(i for i, name in enumerate(_NAMES) if name in block.lower())


def test_dart_ramp_workdays() -> None:
    """``alarm_ramp.dart``'s ``workdays`` is ``freedays.WORKDAYS``."""
    text = (_PHONE / "lib/services/alarm_ramp.dart").read_text()
    match = re.search(r"const Set<int> workdays = \{(.*?)\};", text, re.DOTALL)
    assert match is not None
    assert _weekdays(match.group(1)) == freedays.WORKDAYS


def test_kotlin_workday_stick() -> None:
    """``WorkdayStick.kt``'s ``STICK_DAYS`` is ``freedays.WORKDAYS``."""
    text = (_KOTLIN / "WorkdayStick.kt").read_text()
    match = re.search(r"STICK_DAYS =\s*setOf\((.*?)\)", text, re.DOTALL)
    assert match is not None
    assert _weekdays(match.group(1)) == freedays.WORKDAYS
