"""Read a Dart-written sick-day pool with the Python package and compare.

``phone_app/lib/services/sick_day_pool.dart`` writes the wire format that
``~/src/utils/sickdays`` owns. The Python package is the oracle: it replays
the writer test's edits into a scratch pool, and every reading a gate relies
on (``is_sick_day`` per date, ``sick_days``) has to agree between the two
files. Reads only; writes nothing outside a temporary directory.
"""

from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import sys
import tempfile

import sickdays
from sickdays._paths import Paths

EXPECTED_ARGC = 2
TODAY = date(2026, 10, 16)
DAYS = [TODAY, date(2026, 10, 20), date(2026, 10, 21), date(2026, 10, 23)]


def _never_free(_day: date) -> bool:
    return False


def python_pool(root: Path) -> Path:
    """Write the oracle pool with the edits the Dart writer made."""
    paths = Paths.under(root)
    sickdays.add_sick_day(TODAY, is_free=_never_free, paths=paths, now=TODAY)
    sickdays.add_sick_day(
        date(2026, 10, 20), is_free=_never_free, paths=paths, now=TODAY
    )
    sickdays.add_sick_day(
        date(2026, 10, 21), is_free=_never_free, paths=paths, now=TODAY
    )
    sickdays.remove_sick_day(date(2026, 10, 21), paths=paths, now=TODAY)
    return paths.log


def reading(pool: Path) -> dict[str, object]:
    """Every view of a pool a gate relies on."""
    return {
        "is_sick_day": {
            d.isoformat(): sickdays.is_sick_day(d, log_path=pool) for d in DAYS
        },
        "sick_days": sorted(d.isoformat() for d in sickdays.sick_days(log_path=pool)),
    }


def one_tick_per_write(pool: Path) -> bool:
    """Whether every record's fields share one HLC, as the format requires."""
    log = json.loads(pool.read_text(encoding="utf-8"))
    return all(
        len({hlc for _value, hlc in record["fields"].values()}) == 1
        and not record["deleted"]
        for record in log.values()
    )


def main(argv: list[str]) -> int:
    """Compare the Dart fixture at ``argv[1]`` with the Python oracle."""
    if len(argv) != EXPECTED_ARGC:
        sys.stderr.write("usage: verify.py <dart sick_days.json>\n")
        return 2
    dart = reading(Path(argv[1]))
    with tempfile.TemporaryDirectory() as tmp:
        python = reading(python_pool(Path(tmp)))
    sys.stdout.write(f"dart:   {json.dumps(dart)}\npython: {json.dumps(python)}\n")
    if dart != python:
        sys.stderr.write("MISMATCH: Dart and Python read different pools\n")
        return 1
    if not one_tick_per_write(Path(argv[1])):
        sys.stderr.write("MISMATCH: a Dart record has mixed HLCs or a tombstone\n")
        return 1
    sys.stdout.write("OK: Dart and Python agree\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
