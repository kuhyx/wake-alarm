"""The fire-time record that makes a hard power-off survivable.

The real gap behind item 2 is not the power button itself -- it is that
nothing on disk ever says *"an alarm is ringing right now and was never
dismissed"*. ``wake_state.json`` is written only on **dismissal**, so cutting
power mid-alarm leaves no trace at all: the next boot sees an undismissed day
that looks exactly like a day the alarm had not reached yet, and the catch-up
window has long since closed. Holding the power button therefore *works*, and
that is what this module removes.

So the alarm writes a record the moment it starts ringing, and clears it when
the ring genuinely ends. ``_trigger`` re-fires on a record still marked
``ringing``, ignoring the catch-up window.

**Deliberately no date field.** ``_state.py`` keys its record by a UTC date,
and ``screen_locker/_wake_state.py`` mirrors that helper to read the very same
file from a different repo -- so the UTC basis there is load-bearing and is not
touched. Rather than add a second date key on a different basis, this record
carries only ``fired_at`` as an aware ISO timestamp, and freshness is an
elapsed-time comparison. Timezone-agnostic by construction, so the local
midnight question never arises.

**Bounded, because an unfinished session is not self-clearing.** If the alarm
process dies before dismissal -- Tk cannot open a display, a crash at startup
-- nothing ever runs ``on_close()`` to mark the session finished, and an
unbounded re-fire rule would restart the alarm every single minute forever.
The record is therefore honoured only within ``REFIRE_MAX_AGE_SECONDS`` of
``fired_at``, and the ordinary day / dismissed / workout gates still apply on
top of it.

Signed with :mod:`gatelock.log_integrity`, exactly like ``_state.py``, so the
record cannot simply be edited to say ``dismissed``.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging

from gatelock.log_integrity import compute_entry_hmac, verify_entry_hmac

from wake_alarm._constants import (
    ALARM_SESSION_FILE,
    CLOCK_SKEW_TOLERANCE_SECONDS,
    REFIRE_MAX_AGE_SECONDS,
)

_logger = logging.getLogger(__name__)

STATE_RINGING = "ringing"
STATE_FINISHED = "finished"


def _now() -> datetime:
    """Return the current instant, aware and local. The seam tests patch."""
    return datetime.now(tz=timezone.utc).astimezone()


def _write(entry: dict[str, object]) -> bool:
    """Sign and write *entry*, reporting whether it landed on disk."""
    signature = compute_entry_hmac(entry)
    if signature is not None:
        entry["hmac"] = signature
    else:
        _logger.warning("HMAC key unavailable — saving unsigned alarm session")
    try:
        ALARM_SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        with ALARM_SESSION_FILE.open("w") as handle:
            json.dump(entry, handle, indent=2)
    except OSError as exc:
        _logger.warning("Failed to write the alarm session record: %s", exc)
        return False
    return True


def start_session(correlation: str) -> bool:
    """Record that an alarm has started ringing.

    Args:
        correlation: The derived correlation id for this morning, so the
            record joins up with the JSONL log without a handshake.

    Returns:
        True when the record was written.
    """
    written = _write(
        {
            "state": STATE_RINGING,
            "fired_at": _now().isoformat(),
            "correlation": correlation,
        }
    )
    if written:
        _logger.warning(
            "Alarm session opened (%s) — a power-off now re-fires on boot",
            correlation,
            extra={"event": "session_opened", "correlation": correlation},
        )
    return written


def finish_session() -> bool:
    """Mark the current session finished, however the alarm ended.

    Called from ``on_close()``, so it covers dismissal, the escape hatch and
    SIGTERM alike -- every path where the ring genuinely stopped with the
    machine still up. The one path it cannot cover is the one it exists for:
    power cut mid-alarm, which leaves the record saying ``ringing``.

    Returns:
        True when the record was written.
    """
    entry = load_session()
    if entry is None:
        return False
    return _write(
        {
            "state": STATE_FINISHED,
            "fired_at": entry.get("fired_at"),
            "correlation": entry.get("correlation"),
        }
    )


def load_session() -> dict[str, object] | None:
    """Load and verify the session record.

    Returns:
        The record, or None when it is absent, unreadable, or fails its HMAC
        check. A tampered record is treated as no record: it must not be
        possible to *create* a ringing session by hand either.
    """
    if not ALARM_SESSION_FILE.exists():
        return None
    try:
        with ALARM_SESSION_FILE.open() as handle:
            entry = json.load(handle)
    except (OSError, json.JSONDecodeError):
        _logger.warning("Cannot read the alarm session record")
        return None
    if not isinstance(entry, dict):
        return None
    if verify_entry_hmac(entry):
        return entry
    # An entry with no "hmac" field at all was written unsigned, because no
    # HMAC key was available at fire time. gatelock's verify returns False for
    # that case *and* for a real forgery, and treating them alike would be a
    # silent fail-open: on a machine with no key provisioned, every session
    # record would be unreadable and the power-off defence would simply not
    # exist. Found by running the vmbox harness, where /etc/gatelock is absent.
    #
    # So: unsigned is accepted with a loud warning (it is no weaker than the
    # no-record state it replaces), while a *present but wrong* signature is
    # still rejected outright -- that one really is tampering.
    if "hmac" not in entry:
        _logger.warning(
            "Alarm session is unsigned (no HMAC key on this machine) — "
            "honouring it, but it offers no tamper protection",
            extra={"event": "session_unsigned"},
        )
        return entry
    _logger.warning("Alarm session HMAC verification failed")
    return None


def _fired_at(entry: dict[str, object]) -> datetime | None:
    """Parse the record's ``fired_at``, or None when it is unusable."""
    raw = entry.get("fired_at")
    if not isinstance(raw, str):
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed


def unfinished_session_age(*, now: datetime | None = None) -> float | None:
    """Return how long an unfinished alarm has been ringing, in seconds.

    Args:
        now: Instant to measure against; defaults to the current local time.

    Returns:
        The elapsed seconds when a ringing session is on disk and its
        timestamp is usable, else None. A slightly future-stamped record is
        clamped to zero rather than discarded -- see below.
    """
    entry = load_session()
    if entry is None or entry.get("state") != STATE_RINGING:
        return None
    fired_at = _fired_at(entry)
    if fired_at is None:
        _logger.warning("Alarm session has no usable fired_at; ignoring it")
        return None
    age = ((now if now is not None else _now()) - fired_at).total_seconds()
    if age >= 0:
        return age
    # A record stamped in the future means the clock moved *backwards* since
    # it was written -- NTP correcting after a resume, or RTC-vs-system skew
    # at boot. This machine wakes from hibernate, so that is a routine event,
    # not a broken one. Treating it as "not ringing" would fail open on
    # exactly the scenario this record exists to close: alarm fires on a fast
    # clock, the clock is corrected, and the power-off escape works again.
    # So clamp to zero and let it re-fire.
    if age < -CLOCK_SKEW_TOLERANCE_SECONDS:
        _logger.warning(
            "Alarm session is stamped %.0fs in the future — beyond the "
            "clock-skew tolerance, ignoring it",
            -age,
            extra={"event": "session_clock_skew", "skew_seconds": -age},
        )
        return None
    _logger.info("Alarm session is %.0fs in the future; treating it as fresh", -age)
    return 0.0


def should_refire(*, now: datetime | None = None) -> bool:
    """Report whether an alarm was cut short and must ring again.

    Bounded on purpose: an alarm process that died before dismissal leaves a
    record nothing will ever clear, so without the age limit this would
    restart the alarm every minute indefinitely.

    Args:
        now: Instant to measure against; defaults to the current local time.

    Returns:
        True when a ringing session exists and is younger than the limit.
    """
    age = unfinished_session_age(now=now)
    if age is None:
        return False
    if age > REFIRE_MAX_AGE_SECONDS:
        _logger.info(
            "Ignoring an unfinished alarm session %.0fs old (limit %.0fs)",
            age,
            REFIRE_MAX_AGE_SECONDS,
        )
        return False
    return True
