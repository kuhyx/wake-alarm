"""The phone's newest morning weigh-in, read from the synced alarm record.

The morning session (``phone_app``, ``DOCS-morning-session.md``) publishes
``latest_weight_kg`` -- ``{"date": "yyyy-mm-dd", "kg": 72.4}`` -- on the same
``alarm.json`` the alarm time rides on. This module is the PC-side reader,
built for diet-guard's protein target: it imports this lazily, so the two
packages stay independently installable.

Firebase only. The GitHub mirror has no per-field stamps and is on its way
out; a weigh-in that reached only the mirror is simply not seen yet.

    python -m wake_alarm._weight        # prints {"date": ..., "kg": ...} or nothing
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import sys
from typing import Any

from wake_alarm._alarm_payload import extract_hlc
from wake_alarm._sync_transport import fetch_firebase_logs

_logger = logging.getLogger(__name__)

WEIGHT_FIELD = "latest_weight_kg"


@dataclass(frozen=True)
class Weight:
    """One weigh-in: the local date it was taken and the kilograms typed."""

    date: str
    kg: float
    device_id: str


def _parse_weight(log: dict[str, Any], device_id: str) -> Weight | None:
    """The weigh-in on one device's log, or None if absent or malformed."""
    record = log.get("alarm")
    fields = record.get("fields") if isinstance(record, dict) else None
    pair = fields.get(WEIGHT_FIELD) if isinstance(fields, dict) else None
    value = pair[0] if isinstance(pair, list) and pair else None
    if not isinstance(value, dict):
        return None
    date, kg = value.get("date"), value.get("kg")
    if not isinstance(date, str) or isinstance(kg, bool):
        return None
    if not isinstance(kg, (int, float)):
        return None
    return Weight(date=date, kg=float(kg), device_id=device_id)


def newest_weight(published: list[tuple[str, str]]) -> Weight | None:
    """Pick the most recently stamped weigh-in out of every device's log.

    Ranked by the field's HLC like the alarm is, with ``device_id`` breaking
    exact ties, so two installs never alternate between reads.

    Args:
        published: ``(device_id, raw_json)`` per device, in any order.

    Returns:
        The newest weigh-in, or None if no device published a usable one.
    """
    ranked: list[tuple[str, str, Weight]] = []
    for device_id, raw in published:
        try:
            log = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(log, dict):
            continue
        weight = _parse_weight(log, device_id)
        if weight is not None:
            ranked.append((extract_hlc(log, WEIGHT_FIELD), device_id, weight))
    if not ranked:
        return None
    return max(ranked, key=lambda entry: (entry[0], entry[1]))[2]


def latest_weight() -> Weight | None:
    """The phone's newest weigh-in from Firebase, or None when unreadable."""
    published = fetch_firebase_logs()
    if published is None:
        return None
    weight = newest_weight(published)
    if weight is None:
        _logger.info("No weigh-in published yet")
    return weight


def main() -> int:
    """Print the newest weigh-in as JSON; exit 1 when there is none."""
    weight = latest_weight()
    if weight is None:
        return 1
    sys.stdout.write(json.dumps({"date": weight.date, "kg": weight.kg}) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
