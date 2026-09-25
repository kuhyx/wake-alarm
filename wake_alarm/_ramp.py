"""The baseline wake time, lowered one minute per calendar day to 07:00.

"Cooking the frog": 2026-09-25 is the last 08:00 morning, 2026-09-26 rings
at 07:59, and so on until 2026-11-24 reaches the 07:00 floor, which is then
permanent. The time is a pure function of the date the alarm fires on — no
counter, no stored start date — so neither a reinstall nor a wiped state file
can reset the ramp, and there is nothing that could run away in either
direction.

Every calendar day counts, free days included: counting only rung days would
let free days stall the ramp and move its finish date.

Three copies of this function exist and must agree: this one (PC fallback
and clamp), ``phone_app/lib/services/alarm_ramp.dart`` (the policy the phone
arms and publishes) and ``AlarmRamp.kt`` (the native re-arm after a dismiss,
a free day, a boot or the watchdog). ``tests/test_ramp.py`` parses the other
two and fails when their constants drift from these.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

# The last day at the old 08:00 baseline; each day after it is a minute earlier.
RAMP_ANCHOR: date = date(2026, 9, 25)

# Minutes of day on the anchor date (08:00).
RAMP_START_MINUTES: int = 8 * 60

# The floor the ramp stops at, for good (07:00).
RAMP_FLOOR_MINUTES: int = 7 * 60


def baseline_minutes(day: date) -> int:
    """Return the baseline wake time on *day*, as minutes after midnight.

    Days before the anchor stay at 08:00 rather than extrapolating later:
    the ramp only ever moves the alarm earlier.

    Args:
        day: The local calendar date the alarm fires on.

    Returns:
        Minutes after local midnight, between the floor and the start.
    """
    elapsed = max(0, (day - RAMP_ANCHOR).days)
    return max(RAMP_FLOOR_MINUTES, RAMP_START_MINUTES - elapsed)


def baseline_time(day: date) -> tuple[int, int]:
    """Return the baseline wake time on *day* as ``(hour, minute)``.

    Args:
        day: The local calendar date the alarm fires on.

    Returns:
        The hour and minute of the baseline.
    """
    return divmod(baseline_minutes(day), 60)


def local_today() -> date:
    """Return today's *local* calendar date — the date the phone rings on.

    Never ``_state._today_str()``, which is UTC: between local midnight and
    02:00 in summer it names yesterday, a minute later than today's ramp.

    Returns:
        The system-local date. Also the seam tests patch.
    """
    return datetime.now(tz=UTC).astimezone().date()
