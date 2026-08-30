"""HMAC-signed record of whether the trigger already fired today.

The PC no longer wakes anyone, so this is not a record of a *dismissal* any
more — it is the trigger's once-per-day latch. It has to exist: the tick runs
every minute and the catch-up window is ``TRIGGER_CATCHUP_MINUTES`` wide, so
without a latch the morning routine would be restarted on every tick for the
rest of that window, relaunching the workout lock each time the user finished
it. The alarm's own dismissal used to provide that latch; deleting the alarm
without replacing it would have been a silent regression.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
import logging

from gatelock.log_integrity import (
    compute_entry_hmac,
    verify_entry_hmac,
)

from wake_alarm._constants import WAKE_STATE_FILE

_logger = logging.getLogger(__name__)


def _today_str() -> str:
    """Return today's date as YYYY-MM-DD in UTC."""
    return datetime.now(tz=UTC).strftime("%Y-%m-%d")


def save_trigger_fired(*, fired_at: str) -> bool:
    """Record that the morning routine was started today.

    Args:
        fired_at: ISO timestamp of the tick that started the routine.

    Returns:
        True if saved successfully, False otherwise.
    """
    entry: dict[str, object] = {
        "date": _today_str(),
        "fired_at": fired_at,
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

    _logger.info("Recorded trigger fired at %s", fired_at)
    return True


def load_wake_state() -> dict[str, object] | None:
    """Load and verify today's trigger record.

    Returns the state dict if it exists, is valid (HMAC OK), and is
    for today.  Returns None otherwise.
    """
    if not WAKE_STATE_FILE.exists():
        return None

    try:
        with WAKE_STATE_FILE.open() as f:
            state = json.load(f)
    except OSError, json.JSONDecodeError:
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


def was_trigger_fired_today() -> bool:
    """Check whether the morning routine was already started today."""
    state = load_wake_state()
    if state is None:
        return False
    return state.get("fired_at") is not None
