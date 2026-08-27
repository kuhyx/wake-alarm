"""Guest-side check: does a cut-short alarm re-fire on the next tick?

Run by ``guest_cases.sh`` inside a vmbox sandbox. Prints one line -- three
decisions joined by dashes -- that the shell case compares exactly.

This is the case a VM tests better than the host can: on the real machine the
only honest way to produce an unfinished session is to actually cut the power
mid-alarm. Here the alarm time is deliberately placed hours in the past, so
the catch-up window is closed and **only** an unfinished session can make the
trigger fire.
"""

from __future__ import annotations

import sys

from wake_alarm._alarm_session import finish_session, start_session
from wake_alarm._sync import Alarm
from wake_alarm._trigger import _decide, _now

_HOURS_AGO = 6


def main() -> None:
    """Print before-during-after firing decisions around a session record."""
    now = _now()
    stale = Alarm((now.hour - _HOURS_AGO) % 24, 0, "remote")

    before, _ = _decide(now, stale)
    start_session("wake-vmbox-harness")
    during, _ = _decide(now, stale)
    finish_session()
    after, _ = _decide(now, stale)
    sys.stdout.write(f"{before}-{during}-{after}\n")


if __name__ == "__main__":
    main()
