"""Derive the identifier that joins one morning's PC and phone log lines.

The id is **derived, never generated**: both halves compute it independently
from the resolved alarm instant, so no handshake, no uuid exchange and no
network round-trip is involved. That matters because the two devices must
still agree when sync is down -- which is exactly when the logs are worth
reading.

Local time, matching ``_trigger``'s local-time basis (``_state.py`` keys by
UTC, which is a separate known mismatch tracked in the hardening plan).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

# ``wake-YYYYMMDD-HHMM``. Stable across processes and across devices.
_CORRELATION_FORMAT = "wake-%Y%m%d-%H%M"


def correlation_id(fire_time: datetime) -> str:
    """Build the correlation id for the alarm firing at *fire_time*.

    Args:
        fire_time: The resolved local fire instant for today's alarm.

    Returns:
        A string of the form ``wake-20260826-0700``.
    """
    return fire_time.strftime(_CORRELATION_FORMAT)


def correlation_id_for(hour: int, minute: int, *, now: datetime) -> str:
    """Build the correlation id from an ``(hour, minute)`` alarm on *now*'s date.

    Convenience for callers that hold the synced alarm rather than a resolved
    datetime. The date comes from *now*, so a caller must pass the date the
    alarm belongs to, not merely the current instant.

    Args:
        hour: Alarm hour, 0-23.
        minute: Alarm minute, 0-59.
        now: Any datetime on the alarm's local date.

    Returns:
        The correlation id string.
    """
    return correlation_id(now.replace(hour=hour, minute=minute))
