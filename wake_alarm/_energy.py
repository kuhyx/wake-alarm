"""The phone's newest morning energy rating, read from the synced alarm record.

The morning check-in (``phone_app``, ``DOCS-morning-session.md``) publishes
``latest_energy`` -- ``{"date": "yyyy-mm-dd", "level": 3}``, 1 to 5 -- on the
same ``alarm.json`` the alarm time and ``latest_weight_kg`` ride on. This is
the PC-side reader, the twin of ``_weight.py``: one number, no session shape.

Firebase only, for the same reason as the weight: the GitHub mirror has no
per-field stamps and is on its way out.

    python -m wake_alarm._energy        # prints {"date": ..., "level": ...} or nothing
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import sys

from wake_alarm._constants import ENERGY_FIELD
from wake_alarm._field_reader import latest_field, newest_field

MIN_LEVEL = 1
MAX_LEVEL = 5


@dataclass(frozen=True)
class Energy:
    """One rating: the local date it was given and the 1-5 level tapped."""

    date: str
    level: int
    device_id: str


def _parse_energy(value: object, device_id: str) -> Energy | None:
    """The rating out of one device's ``latest_energy`` value, or None."""
    if not isinstance(value, dict):
        return None
    date, level = value.get("date"), value.get("level")
    if not isinstance(date, str) or isinstance(level, bool):
        return None
    if not isinstance(level, int) or not MIN_LEVEL <= level <= MAX_LEVEL:
        return None
    return Energy(date=date, level=level, device_id=device_id)


def newest_energy(published: list[tuple[str, str]]) -> Energy | None:
    """The most recently stamped rating across every device's log."""
    return newest_field(published, ENERGY_FIELD, _parse_energy)


def latest_energy() -> Energy | None:
    """The phone's newest rating from Firebase, or None when unreadable."""
    return latest_field(ENERGY_FIELD, _parse_energy, what="energy rating")


def main() -> int:
    """Print the newest rating as JSON; exit 1 when there is none."""
    energy = latest_energy()
    if energy is None:
        return 1
    sys.stdout.write(json.dumps({"date": energy.date, "level": energy.level}) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
