"""Format the skip-window countdown shown on the lock screen.

Split out of ``_alarm.py`` for the 250-line cap, and because the wording is
load-bearing: once the window closes the label must stop implying a reward is
still available while making clear the alarm has *not* stopped.
"""

from __future__ import annotations

from wake_alarm._constants import DISMISS_CODE_REFRESH_SECONDS, DISMISS_WINDOW_MINUTES

# Demo mode compresses the schedule so a manual test does not take half an
# hour, without changing any production timing.
DEMO_REFRESH_MS = 10_000
DEMO_WINDOW_MS = 30_000
DEMO_WINDOW_SECONDS = 30.0

NO_SKIP_TEXT = "No skip available - type the code to stop the alarm"
WINDOW_CLOSED_INFO = "Skip window closed - type the code to stop the alarm"
NO_SKIP_STATUS = "No workout skip today."


def remaining_seconds(elapsed: float, window: float) -> float:
    """Seconds left in the skip window, never negative.

    Args:
        elapsed: Seconds since the alarm started.
        window: Total length of the skip window in seconds.

    Returns:
        Remaining seconds, floored at zero.
    """
    return max(0.0, window - elapsed)


def countdown_text(remaining: float, *, earnable: bool) -> str:
    """Build the timer label for the current state.

    Args:
        remaining: Seconds left in the skip window.
        earnable: Whether a skip can still be earned.

    Returns:
        The label text.
    """
    if not earnable or remaining <= 0:
        return NO_SKIP_TEXT
    minutes = int(remaining) // 60
    seconds = int(remaining) % 60
    return f"Skip window: {minutes:02d}:{seconds:02d}"


def refresh_interval_ms(*, demo_mode: bool) -> int:
    """Milliseconds between challenge refreshes.

    Args:
        demo_mode: True for the shortened manual-test schedule.

    Returns:
        The delay to pass to ``after()``.
    """
    if demo_mode:
        return DEMO_REFRESH_MS
    return DISMISS_CODE_REFRESH_SECONDS * 1000


def skip_window_ms(*, demo_mode: bool) -> int:
    """Milliseconds until the workout-skip reward expires.

    Args:
        demo_mode: True for the shortened manual-test schedule.

    Returns:
        The delay to pass to ``after()``.
    """
    if demo_mode:
        return DEMO_WINDOW_MS
    return DISMISS_WINDOW_MINUTES * 60 * 1000


def skip_window_seconds(*, demo_mode: bool) -> float:
    """Length of the skip window in seconds.

    Args:
        demo_mode: True for the shortened manual-test schedule.

    Returns:
        The window length.
    """
    if demo_mode:
        return DEMO_WINDOW_SECONDS
    return float(DISMISS_WINDOW_MINUTES * 60)
