"""Decide whether the alarm should run, and parse its CLI.

Split out of ``_alarm.py`` so the gate is testable without constructing a
window, and to keep that module under the 250-line cap.

Note ``_should_run_alarm`` has deliberately **no time gate**: the trigger owns
"is it time?", and this owns "should it run at all today?". That separation is
why ``wake-alarm.service`` must never get an ``[Install]`` section -- with no
time gate, a ``WantedBy=`` would fire the alarm at login.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import logging

from wake_alarm._constants import ALARM_DAYS
from wake_alarm._state import was_alarm_dismissed_today, was_workout_logged_today

_logger = logging.getLogger(__name__)


def is_alarm_day(*, now: datetime | None = None) -> bool:
    """Report whether today is configured as an alarm day.

    Args:
        now: Instant to test; defaults to the current local time.

    Returns:
        True when today's weekday is in ``ALARM_DAYS``.
    """
    moment = now if now is not None else datetime.now(tz=timezone.utc).astimezone()
    return moment.weekday() in ALARM_DAYS


def should_run_alarm() -> bool:
    """Decide whether the alarm should sound at all today.

    Returns:
        True unless today is not an alarm day, the alarm was already
        dismissed, or the workout was already logged.
    """
    if not is_alarm_day():
        _logger.info("Not an alarm day. Exiting.")
        return False
    if was_alarm_dismissed_today():
        _logger.info("Alarm already dismissed today. Exiting.")
        return False
    if was_workout_logged_today():
        _logger.info("Workout already logged today. Skipping alarm.")
        return False
    return True


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse CLI arguments for the alarm daemon.

    Args:
        argv: Argument list without the program name.

    Returns:
        The parsed namespace.
    """
    parser = argparse.ArgumentParser(description="Wake alarm daemon.")
    parser.add_argument(
        "--production",
        action="store_true",
        help="Production mode (default; kept for systemd compatibility).",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run with a smaller window and shorter timers.",
    )
    parser.add_argument(
        "--trigger-now",
        action="store_true",
        help="Bypass the day/dismiss gate and fire the alarm immediately.",
    )
    return parser.parse_args(argv)
