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
import sys

from wake_alarm._field_reader import latest_field, newest_field

WEIGHT_FIELD = "latest_weight_kg"


@dataclass(frozen=True)
class Weight:
    """One weigh-in: the local date it was taken and the kilograms typed."""

    date: str
    kg: float
    device_id: str


def _parse_weight(value: object, device_id: str) -> Weight | None:
    """The weigh-in out of one device's ``latest_weight_kg`` value, or None."""
    if not isinstance(value, dict):
        return None
    date, kg = value.get("date"), value.get("kg")
    if not isinstance(date, str) or isinstance(kg, bool):
        return None
    if not isinstance(kg, (int, float)):
        return None
    return Weight(date=date, kg=float(kg), device_id=device_id)


def newest_weight(published: list[tuple[str, str]]) -> Weight | None:
    """The most recently stamped weigh-in across every device's log."""
    return newest_field(published, WEIGHT_FIELD, _parse_weight)


def latest_weight() -> Weight | None:
    """The phone's newest weigh-in from Firebase, or None when unreadable."""
    return latest_field(WEIGHT_FIELD, _parse_weight, what="weigh-in")


def main() -> int:
    """Print the newest weigh-in as JSON; exit 1 when there is none."""
    weight = latest_weight()
    if weight is None:
        return 1
    sys.stdout.write(json.dumps({"date": weight.date, "kg": weight.kg}) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
