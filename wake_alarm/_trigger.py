"""Per-minute tick that fires the morning routine at the phone's alarm time.

Run by ``wake-alarm-trigger.timer`` once a minute. Exits in milliseconds on an
ordinary tick; on the alarm minute it starts ``morning-routine.service`` and
exits.

Why a timer rather than a resident scheduler: each tick is a fresh, stateless
process, so there is no long-lived daemon to die silently and no wall-clock
jump to reason about when the machine suspends and resumes.

Why it starts the *orchestrator* and not ``wake-alarm.service``: the
orchestrator runs the alarm first and the workout lock afterwards, so the two
never fight for the fullscreen. Bypassing it is the exact failure ``CLAUDE.md``
documents. Starting an already-running unit is a no-op, which also means an
alarm currently on screen needs no extra dedupe bookkeeping.

All times are **local**. The phone stores a wall-clock H:M, so the fire instant
must be built in the same timezone the user reads off their phone.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import logging
import subprocess
import sys

from wake_alarm._alarm_session import should_refire
from wake_alarm._constants import (
    ALARM_DAYS,
    FALLBACK_ALARM_HOUR,
    TRIGGER_CATCHUP_MINUTES,
    TRIGGER_TARGET_UNIT,
)
from wake_alarm._logging_setup import configure_logging
from wake_alarm._state import (
    was_alarm_dismissed_today,
    was_workout_logged_today,
)
from wake_alarm._sync import Alarm, get_alarm

_logger = logging.getLogger(__name__)


def _now() -> datetime:
    """Return the current time as an aware datetime in the system's timezone.

    Aware-and-local, not naive: the phone stores a wall-clock H:M, so the fire
    instant has to be built in the timezone the user reads off their phone —
    but carrying the offset explicitly keeps the comparisons unambiguous.

    Returns:
        The current local time, with tzinfo set. Also the seam tests patch.
    """
    return datetime.now(tz=timezone.utc).astimezone()


def _fire_window(alarm: Alarm, now: datetime) -> tuple[datetime, datetime]:
    """Compute today's fire instant and the end of its catch-up window.

    Args:
        alarm: The resolved alarm time.
        now: Current local time, used only for its date.

    Returns:
        A (fire_at, window_end) pair in local time.
    """
    # Drop to a naive wall-clock time before substituting H:M, then let
    # astimezone() re-derive the offset. Calling replace() straight on an
    # aware datetime would keep *now*'s UTC offset, which is wrong across a
    # DST boundary — e.g. deciding a 06:40 alarm from a 03:00 tick on the
    # night the clocks move.
    fire_at = (
        now.replace(tzinfo=None)
        .replace(hour=alarm.hour, minute=alarm.minute, second=0, microsecond=0)
        .astimezone()
    )
    return fire_at, fire_at + timedelta(minutes=TRIGGER_CATCHUP_MINUTES)


def _skip_reason(now: datetime) -> str | None:
    """Return why the alarm must not fire right now, or None if it may.

    Checks only the gates that are independent of the clock: the day gate and
    the two "already handled today" gates shared with ``_alarm.py``.

    Args:
        now: Current local time.

    Returns:
        A human-readable reason, or None when nothing blocks firing.
    """
    if now.weekday() not in ALARM_DAYS:
        return "not an alarm day"
    if was_alarm_dismissed_today():
        return "alarm already dismissed today"
    if was_workout_logged_today():
        return "workout already logged today"
    return None


def _start_target_unit() -> bool:
    """Start the morning routine unit.

    Returns:
        True if systemd accepted the start, False otherwise. A failure is
        logged and swallowed: the next tick retries, and the catch-up window
        means a transient failure does not cost the whole wake-up.
    """
    cmd = ["systemctl", "--user", "start", TRIGGER_TARGET_UNIT]
    try:
        result = subprocess.run(cmd, check=False, capture_output=True)
    except OSError:
        _logger.warning("Failed to run %s", " ".join(cmd), exc_info=True)
        return False
    if result.returncode != 0:
        _logger.warning(
            "%s failed (rc=%d): %s",
            " ".join(cmd),
            result.returncode,
            result.stderr.decode("utf-8", "replace").strip(),
        )
        return False
    return True


def _decide(now: datetime, alarm: Alarm) -> tuple[bool, str]:
    """Decide whether this tick should fire the alarm.

    Args:
        now: Current local time.
        alarm: The resolved alarm time.

    Returns:
        A (should_fire, reason) pair; *reason* explains the decision either
        way and is what ``--dry-run`` prints.
    """
    skip = _skip_reason(now)
    if skip is not None:
        return False, skip

    # An alarm that was cut short -- almost always a power-button press or a
    # hard power-off -- left a "ringing" session record that nothing cleared.
    # It re-fires regardless of the catch-up window, because the whole point is
    # that the machine may have been off for the rest of that window. The day /
    # dismissed / workout gates above still apply, and the record itself is
    # age-bounded, so this cannot loop forever on a crashed alarm.
    if should_refire(now=now):
        return True, "an earlier alarm was cut short and never dismissed"

    fire_at, window_end = _fire_window(alarm, now)
    if now < fire_at:
        return False, f"alarm {alarm} is still ahead"
    if now >= window_end:
        return False, (
            f"alarm {alarm} passed over "
            f"{TRIGGER_CATCHUP_MINUTES} minutes ago — window closed"
        )
    return True, f"alarm {alarm} is due (since {fire_at:%H:%M})"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse CLI arguments for the trigger."""
    parser = argparse.ArgumentParser(
        description="Fire the morning routine at the phone's alarm time."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the decision without starting anything.",
    )
    return parser.parse_args(argv)


def _clamp_to_baseline(alarm: Alarm) -> Alarm:
    """Refuse to let any resolved alarm land later than the baseline.

    The phone bakes in ``FALLBACK_ALARM_HOUR`` and only ever ratchets *earlier*,
    so a synced value later than the baseline means something is wrong — a
    stale record from before the policy landed, a half-written payload, or a
    tampered store. Whatever the cause, the safe direction is unambiguous:
    honour it if it is earlier, clamp it if it is later.

    This is the PC half of the watchdog. Without it the PC would faithfully
    reproduce a bad remote value, and the one thing the design forbids —
    the alarm silently moving later — would be reachable through sync.

    Args:
        alarm: The alarm as resolved by ``get_alarm``.

    Returns:
        The same alarm, or the baseline when the resolved time is later.
    """
    if (alarm.hour, alarm.minute) <= (FALLBACK_ALARM_HOUR, 0):
        return alarm
    _logger.warning(
        "Resolved alarm %02d:%02d is later than the %02d:00 baseline "
        "(source=%s) — clamping. The phone can only move it earlier, so a "
        "later value means a stale or tampered record.",
        alarm.hour,
        alarm.minute,
        FALLBACK_ALARM_HOUR,
        alarm.source,
    )
    return Alarm(FALLBACK_ALARM_HOUR, 0, f"clamped-{alarm.source}")


def main() -> None:
    """Entry point for one timer tick."""
    configure_logging(component="trigger")
    args = _parse_args(sys.argv[1:])

    now = _now()
    alarm = _clamp_to_baseline(get_alarm())
    should_fire, reason = _decide(now, alarm)

    if args.dry_run:
        verdict = "WOULD FIRE" if should_fire else "not firing"

        sys.stdout.write(f"{now:%Y-%m-%d %H:%M} — {verdict}: {reason}\n")
        return

    if not should_fire:
        _logger.debug("Not firing: %s", reason)
        return

    # The one moment a degraded read is worth shouting about: we are firing
    # now, and the time we are firing at did not come from the phone.
    if alarm.source not in {"remote", "cache"}:
        _logger.warning(
            "Firing on a degraded alarm source (%s) — the phone's alarm "
            "could not be read; check ~/.config/wake_alarm/sync.json",
            alarm.source,
        )

    _logger.warning("Firing %s: %s", TRIGGER_TARGET_UNIT, reason)
    _start_target_unit()


if __name__ == "__main__":
    main()
