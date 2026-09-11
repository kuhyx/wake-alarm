"""Replay the fixture's edits through the Python rules and compare the pools.

The Dart port in phone_app is a second implementation of ~/src/utils/freedays'
policy, so it is checked against the original rather than against itself.
Comparing Dart's *own* count to what Python reads from Dart's file cannot
catch a drift in what Dart writes -- both sides would agree on the wrong
record. So the Python package is the oracle: it performs the same
mark/release sequence into a scratch pool, and every semantic reading of the
two logs (free set, spent set, remaining, is_free_day) has to agree.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
import sys
import tempfile

import freedays
from freedays._api import load, mark, release
from freedays._budget import free_days_in_year, remaining, spent_days_in_year
from freedays._paths import Paths

EXPECTED_ARGC = 2

# Mirror of free_day_interop_writer_test.dart, one call per policy branch.
TODAY = date(2026, 9, 11)
DAYS = [date(2026, 9, 11), date(2026, 9, 12), date(2026, 9, 13), date(2026, 9, 14)]


def python_pool(root: Path) -> Path:
    """Write the oracle pool with the same edits the Dart fixture made."""
    paths = Paths(
        log=root / "free_days.json",
        device_id=root / "device_id",
        audit=root / "audit.jsonl",
        hmac_key=root / "hmac.key",
        sync_state=root / "sync_state.json",
    )
    mark(date(2026, 9, 12), reason="from dart", paths=paths, now=TODAY)
    mark(TODAY, paths=paths, now=TODAY)
    mark(date(2026, 9, 13), paths=paths, now=TODAY)
    release(date(2026, 9, 13), paths=paths, now=TODAY)
    mark(date(2026, 9, 14), paths=paths, now=TODAY)
    release(date(2026, 9, 14), paths=paths, now=date(2026, 9, 14))
    return paths.log


def reading(pool: Path) -> dict[str, object]:
    """Every semantic view of a pool that a gate or the picker relies on."""
    log = load(pool)
    return {
        "remaining": remaining(log, 2026),
        "spent": [d.isoformat() for d in spent_days_in_year(log, 2026)],
        "free": [d.isoformat() for d in free_days_in_year(log, 2026)],
        "is_free_day": {
            d.isoformat(): freedays.is_free_day(d, log_path=pool) for d in DAYS
        },
        "reason": freedays.lookup(date(2026, 9, 12), log_path=pool).reason,
    }


def say(line: str) -> None:
    """One report line; the shell wrapper shows these verbatim."""
    sys.stdout.write(line + "\n")


def main(argv: list[str]) -> int:
    """Compare the Dart-written pool at ``argv[1]`` with the oracle."""
    if len(argv) != EXPECTED_ARGC:
        sys.stderr.write(f"usage: {argv[0]} <free_days.json>\n")
        return 2
    dart = reading(Path(argv[1]))
    with tempfile.TemporaryDirectory() as tmp:
        python = reading(python_pool(Path(tmp)))
    ok = True
    for key, expected in python.items():
        same = dart[key] == expected
        ok = ok and same
        say(f"{'ok ' if same else 'XX '}{key}: dart={dart[key]} python={expected}")
    say("free-day interop: " + ("OK" if ok else "MISMATCH"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
