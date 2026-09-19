"""Pick one field's newest value out of every device's synced log.

``_weight`` and ``_energy`` each read a single ``{date, value}`` pair the
phone publishes on ``alarm.json``; everything but the parse is the same, and
pylint rightly flagged the copy. This is the shared half: JSON in per device,
one winner out, ranked by the field's HLC with ``device_id`` breaking exact
ties so two installs never alternate between reads.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from wake_alarm._alarm_payload import extract_hlc
from wake_alarm._sync_transport import fetch_firebase_logs

if TYPE_CHECKING:
    from collections.abc import Callable

_logger = logging.getLogger(__name__)


def field_value(log: dict[str, Any], field: str) -> object:
    """The value half of one ``(value, HLC)`` pair on the alarm record, or None."""
    record = log.get("alarm")
    fields = record.get("fields") if isinstance(record, dict) else None
    pair = fields.get(field) if isinstance(fields, dict) else None
    return pair[0] if isinstance(pair, list) and pair else None


def newest_field[T](
    published: list[tuple[str, str]],
    field: str,
    parse: Callable[[object, str], T | None],
) -> T | None:
    """The most recently stamped ``field`` across every device's log.

    Args:
        published: ``(device_id, raw_json)`` per device, in any order.
        field: The crdt_sync field name.
        parse: Turns the raw value plus its device id into the result, or
            None when the shape is not usable -- an unusable device never
            outranks a usable one.
    """
    ranked: list[tuple[str, str, T]] = []
    for device_id, raw in published:
        try:
            log = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(log, dict):
            continue
        parsed = parse(field_value(log, field), device_id)
        if parsed is not None:
            ranked.append((extract_hlc(log, field), device_id, parsed))
    if not ranked:
        return None
    return max(ranked, key=lambda entry: (entry[0], entry[1]))[2]


def latest_field[T](
    field: str, parse: Callable[[object, str], T | None], *, what: str
) -> T | None:
    """``newest_field`` over a live Firebase read; None when unreadable."""
    published = fetch_firebase_logs()
    if published is None:
        return None
    value = newest_field(published, field, parse)
    if value is None:
        _logger.info("No %s published yet", what)
    return value
