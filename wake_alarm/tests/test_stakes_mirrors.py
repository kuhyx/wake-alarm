"""The phone's copies of the wake-enforcement numbers agree with the PC's.

The stakes card and the ring line (``phone_app/lib/services/stakes.dart``)
promise numbers the PC enforces, and the native stick
(``Stakes.kt``) decides with some of them; neither can import
``wake_alarm._constants``. This parses their source and compares, so a
number changed on one side fails here instead of on a morning.
See ``DOCS-wake-enforcement.md``.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import re

from wake_alarm import _constants

_PHONE = Path(__file__).resolve().parents[2] / "phone_app"
_DART = _PHONE / "lib/services/stakes.dart"
_KOTLIN = _PHONE / "android/app/src/main/kotlin/com/kuhy/wake_alarm_sync/Stakes.kt"


def _match(text: str, pattern: str) -> re.Match[str]:
    """Return *pattern*'s match in *text*, failing with the pattern when absent."""
    found = re.search(pattern, text)
    assert found is not None, f"not found: {pattern}"
    return found


def _dart_duration(name: str) -> timedelta:
    """Read ``const <name> = Duration(<unit>: <n>);`` from ``stakes.dart``."""
    found = _match(_DART.read_text(), rf"const {name} = Duration\((\w+): (\d+)\);")
    return timedelta(**{found.group(1): int(found.group(2))})


def _dart_clock(name: str) -> tuple[int, int]:
    """Read ``const ClockTime <name> = (hour: h, minute: m);``."""
    pattern = rf"const ClockTime {name} = \(hour: (\d+), minute: (\d+)\);"
    found = _match(_DART.read_text(), pattern)
    return int(found.group(1)), int(found.group(2))


def _dart_int(name: str) -> int:
    """Read ``const <name> = <n>;`` from ``stakes.dart``."""
    return int(_match(_DART.read_text(), rf"const {name} = (\d+);").group(1))


def _kotlin(name: str) -> str:
    """Read ``const val <name> = <literal>`` from ``Stakes.kt``, unquoted."""
    found = _match(_KOTLIN.read_text(), rf"const val {name} = \"?([\w-]+?)L?\"?\n")
    return found.group(1)


def test_dart_durations() -> None:
    """Every Dart ``Duration`` equals its Python ``timedelta``."""
    assert _dart_duration("stickGrace") == _constants.SESSION_NONE_GRACE
    assert _dart_duration("provisionalGrace") == _constants.SESSION_PROVISIONAL_GRACE
    assert (
        _dart_duration("pcPhoneSilentAfter") == _constants.FALLBACK_PHONE_SILENT_AFTER
    )
    assert _dart_duration("pcRingCap") == _constants.FALLBACK_RING_CAP


def test_dart_times_of_day() -> None:
    """The carrot's cap and end match the PC's ``(hour, minute)`` tuples."""
    assert _dart_clock("provisionalCap") == tuple(_constants.SESSION_PROVISIONAL_CAP)
    assert _dart_clock("completedUntil") == tuple(_constants.SESSION_COMPLETED_UNTIL)


def test_dart_counts() -> None:
    """The lockdown span and the reason length match."""
    assert _dart_int("stickLockdownMaxDays") == _constants.STICK_LOCKDOWN_MAX_DAYS
    assert _dart_int("escapeReasonMinChars") == _constants.ESCAPE_REASON_MIN_CHARS


def test_dart_escape_last_day() -> None:
    """``escapeHatchLastDay`` is ``ESCAPE_HATCH_LAST_DAY``."""
    pattern = r"final escapeHatchLastDay = DateTime\((\d+), (\d+), (\d+)\);"
    found = _match(_DART.read_text(), pattern)
    dart = date(*(int(found.group(i)) for i in (1, 2, 3)))
    assert dart == _last_day()


def test_kotlin_copies() -> None:
    """The native stick's grace, lockdown span and hatch end match too."""
    grace = timedelta(minutes=int(_kotlin("STICK_GRACE_MINUTES")))
    assert grace == _constants.SESSION_NONE_GRACE
    assert int(_kotlin("STICK_LOCKDOWN_MAX_DAYS")) == _constants.STICK_LOCKDOWN_MAX_DAYS
    assert date.fromisoformat(_kotlin("ESCAPE_HATCH_LAST_DAY")) == _last_day()


def _last_day() -> date:
    """``ESCAPE_HATCH_LAST_DAY`` as a date, whether stored as one or as ISO text."""
    value = _constants.ESCAPE_HATCH_LAST_DAY
    return value if isinstance(value, date) else date.fromisoformat(str(value))
