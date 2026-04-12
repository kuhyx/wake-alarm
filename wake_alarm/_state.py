"""HMAC-signed state management for the weekend wake alarm."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging

from python_pkg.shared.log_integrity import (
    compute_entry_hmac,
    verify_entry_hmac,
)
from python_pkg.wake_alarm._constants import WAKE_STATE_FILE

_logger = logging.getLogger(__name__)


def _today_str() -> str:
    """Return today's date as YYYY-MM-DD in UTC."""
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")


def save_wake_state(
    *,
    dismissed_at: str | None,
    skip_workout: bool,
) -> bool:
    """Write today's wake state with HMAC signature.

    Args:
        dismissed_at: ISO time when alarm was dismissed, or None.
        skip_workout: Whether the user earned a workout skip.

    Returns:
        True if saved successfully, False otherwise.
    """
    entry: dict[str, object] = {
        "date": _today_str(),
        "dismissed_at": dismissed_at,
        "skip_workout": skip_workout,
    }
    signature = compute_entry_hmac(entry)
    if signature is not None:
        entry["hmac"] = signature
    else:
        _logger.warning("HMAC key unavailable — saving unsigned wake state")

    try:
        with WAKE_STATE_FILE.open("w") as f:
            json.dump(entry, f, indent=2)
    except OSError as exc:
        _logger.warning("Failed to save wake state: %s", exc)
        return False

    _logger.info(
        "Saved wake state: dismissed=%s skip=%s",
        dismissed_at,
        skip_workout,
    )
    return True


def load_wake_state() -> dict[str, object] | None:
    """Load and verify today's wake state.

    Returns the state dict if it exists, is valid (HMAC OK), and is
    for today.  Returns None otherwise.
    """
    if not WAKE_STATE_FILE.exists():
        return None

    try:
        with WAKE_STATE_FILE.open() as f:
            state = json.load(f)
    except (OSError, json.JSONDecodeError):
        _logger.warning("Cannot read wake state file")
        return None

    if not isinstance(state, dict):
        return None

    if state.get("date") != _today_str():
        return None

    if not verify_entry_hmac(state):
        _logger.warning("Wake state HMAC verification failed")
        return None

    return state


def has_workout_skip_today() -> bool:
    """Check if the user earned a workout skip for today."""
    state = load_wake_state()
    if state is None:
        return False
    return bool(state.get("skip_workout"))


def was_alarm_dismissed_today() -> bool:
    """Check if the alarm was already dismissed today."""
    state = load_wake_state()
    if state is None:
        return False
    return state.get("dismissed_at") is not None
