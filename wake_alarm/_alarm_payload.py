"""Parse the alarm out of the ``crdt_sync`` log the phone publishes.

Split out of ``_sync.py`` so that module keeps to fetching, caching and
fallback: everything here is pure, takes text or already-parsed JSON, and
touches neither the network nor the disk. That makes the wire format testable
on its own, which matters because a misparse here does not raise — it
silently resolves to the wrong wake-up time.

The published shape is one ``crdt_sync`` record::

    {"alarm": {"fields": {"alarm_hour": [7, "<hlc>"], "alarm_minute": [30, "<hlc>"]}}}

Every field is a ``(value, HLC)`` pair. Ranking across devices uses the HLC
rather than the value, so the alarm that wins is the one *set* most recently.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
import logging
from typing import Any

from wake_alarm._constants import MAX_HOUR, MAX_MINUTE, MIN_HOUR, MIN_MINUTE

_logger = logging.getLogger(__name__)

# Keys inside the crdt_sync log the phone writes.
RECORD_ID = "alarm"
HOUR_FIELD = "alarm_hour"
MINUTE_FIELD = "alarm_minute"

# A crdt_sync field is a (value, HLC) pair.
_HLC_PAIR_LENGTH = 2


def in_range(hour: int, minute: int) -> bool:
    """Check that an (hour, minute) pair is a real wall-clock time.

    Guards both readers: a malformed sync payload and a corrupted cache must
    never become a fire time.

    Args:
        hour: Candidate hour.
        minute: Candidate minute.

    Returns:
        True if both values are within a 24-hour clock.
    """
    return MIN_HOUR <= hour <= MAX_HOUR and MIN_MINUTE <= minute <= MAX_MINUTE


def _field_pair(log: dict[str, Any], field: str) -> list[Any] | None:
    """Return the raw ``(value, HLC)`` pair for [field], if well-shaped.

    Args:
        log: The parsed log JSON.
        field: Field name to look up.

    Returns:
        The pair as a list, or None if any level of the shape is unexpected.
    """
    record = log.get(RECORD_ID)
    if not isinstance(record, dict):
        return None
    fields = record.get("fields")
    if not isinstance(fields, dict):
        return None
    pair = fields.get(field)
    return pair if isinstance(pair, list) and pair else None


def extract_field(log: dict[str, Any], field: str) -> int | None:
    """Pull one integer field out of the phone's crdt_sync log.

    Args:
        log: The parsed log JSON.
        field: Field name to extract (e.g. ``alarm_hour``).

    Returns:
        The integer value, or None if anything about the shape is unexpected.
    """
    pair = _field_pair(log, field)
    if pair is None:
        return None
    value = pair[0]
    # bool is an int subclass; an alarm hour of True would be nonsense.
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def extract_hlc(log: dict[str, Any], field: str) -> str:
    """Pull one field's HLC stamp out of the phone's crdt_sync log.

    HLC strings are ``<iso>-<counter>-<deviceId>`` and sort lexicographically
    in timestamp order, which is what lets [newest_alarm] rank two devices'
    publications against each other.

    Args:
        log: The parsed log JSON.
        field: Field name whose stamp to read.

    Returns:
        The HLC string, or ``""`` if absent or the wrong shape -- which sorts
        below every real stamp, so a device publishing a malformed pair never
        outranks one publishing a good pair.
    """
    pair = _field_pair(log, field)
    if pair is None or len(pair) < _HLC_PAIR_LENGTH:
        return ""
    hlc = pair[1]
    return hlc if isinstance(hlc, str) else ""


def parse_log(raw: str) -> tuple[int, int] | None:
    """Parse one device's published log into an (hour, minute) pair.

    Args:
        raw: The raw JSON text returned by the backend.

    Returns:
        The (hour, minute) pair, or None if the payload is malformed or the
        values are out of range.
    """
    try:
        log = json.loads(raw)
    except json.JSONDecodeError:
        _logger.warning("Synced alarm is not valid JSON")
        return None
    if not isinstance(log, dict):
        return None
    hour = extract_field(log, HOUR_FIELD)
    minute = extract_field(log, MINUTE_FIELD)
    if hour is None or minute is None:
        _logger.warning("Synced alarm is missing hour/minute fields")
        return None
    if not in_range(hour, minute):
        _logger.warning("Synced alarm out of range: %d:%d", hour, minute)
        return None
    return hour, minute


def hlc_instant(hlc: str) -> float | None:
    """Wall-clock instant an HLC stamp was minted, as epoch seconds.

    HLC strings are ``<iso>-<counter>-<deviceId>``, and the ISO part ends at
    its ``Z`` -- which is what makes this splittable at all, since the ISO
    date itself contains the same ``-`` the fields are joined with.

    Args:
        hlc: The stamp, or ``""`` when the field carried none.

    Returns:
        Epoch seconds, or None when the stamp is absent or unparsable. None
        means "cannot tell how old this is", and callers treat that as
        trustworthy rather than expired -- refusing to act on an alarm we
        merely failed to date would be a worse failure than acting on it.
    """
    iso, separator, _ = hlc.partition("Z")
    if not separator:
        return None
    try:
        return datetime.fromisoformat(iso).replace(tzinfo=UTC).timestamp()
    except ValueError:
        return None


def newest_alarm(
    published: list[tuple[str, str]],
) -> tuple[int, int, float | None] | None:
    """Pick the most recently published alarm out of every device's log.

    Ranked by the hour field's HLC stamp, which orders by wall time and then
    by counter -- so the winner is the device that set the alarm last, not
    whichever directory the backend happened to list first. A device whose
    payload does not parse is skipped rather than being allowed to win with a
    malformed value.

    Args:
        published: ``(device_id, raw_json)`` for every device that has
            published, in any order.

    Returns:
        The newest ``(hour, minute, published_at)``, where ``published_at`` is
        epoch seconds from the winning HLC (or None if it carried no readable
        stamp). None if no device published a usable alarm.
    """
    ranked: list[tuple[str, str, tuple[int, int]]] = []
    for device_id, raw in published:
        parsed = parse_log(raw)
        if parsed is None:
            _logger.info("Ignoring unusable alarm published by %r", device_id)
            continue
        ranked.append((extract_hlc(json.loads(raw), HOUR_FIELD), device_id, parsed))
    if not ranked:
        return None
    # device_id breaks an exact HLC tie deterministically, so two devices
    # stamped in the same millisecond don't alternate between ticks.
    hlc, winner, alarm = max(ranked, key=lambda entry: (entry[0], entry[1]))
    _logger.info("Using the alarm published by %r (hlc %s)", winner, hlc or "none")
    return (*alarm, hlc_instant(hlc))
