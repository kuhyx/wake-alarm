"""Cross-check the Dart sick-day pool against the Python package, both ways.

``phone_app/lib/services/sick_day_pool.dart`` writes the wire format that
``~/src/utils/sickdays`` owns (0.2.0, with the per-locker ``keep`` set). The
Python package is the oracle in both directions:

``dart <dart.json>``
    Replays the Dart writer test's edits into a scratch pool and fails on any
    disagreement in a reading a gate relies on (``is_sick_day``,
    ``kept_lockers``, ``stands_down`` per locker, ``sick_days``), or on a
    wire-format slip: an unsorted keep, a mark/clear with mixed ticks, or a
    keep-only edit that re-stamped ``state``.
``write <out.json>``
    Writes a Python pool for the Dart reader test, including the records a
    0.2.0 writer can no longer produce: a 0.1.0 record with no ``keep``, a
    stale ``keep`` (an old client re-added the day) and a malformed one.
``read <python.json> <dart-reading.json>``
    Compares the Dart reader's verdicts with Python's for that same pool.

Every sickdays call gets an explicit ``paths=`` / ``log_path=``: a default
would resolve the real pool under ``~/.local/share/sickdays``. ``check.sh``
also points ``HOME`` at a scratch directory, as a second line of defence.
"""

from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import sys
import tempfile

from crdt_sync import Hlc
import sickdays
from sickdays._paths import Paths

TODAY = date(2026, 10, 16)
DART_DAYS = [TODAY, *(date(2026, 10, d) for d in (20, 21, 22, 23))]
PY_DAYS = [date(2026, 10, d) for d in (20, 22, 23, 24, 25, 26)]
#: Dart-written records that were keep-only edited after the mark.
KEEP_EDITED = {"2026-10-22"}
USAGE = (
    "usage: verify.py dart <dart.json> | write <out.json> | "
    "read <python.json> <dart-reading.json>\n"
)


def _never_free(_day: date) -> bool:
    return False


def _add(paths: Paths, day: date, keep: tuple[str, ...] = ()) -> None:
    sickdays.add_sick_day(day, keep=keep, is_free=_never_free, paths=paths, now=TODAY)


def dart_oracle(root: Path) -> Path:
    """The Dart writer test's edits, made by the Python package."""
    paths = Paths.under(root)
    _add(paths, TODAY)
    _add(paths, date(2026, 10, 20), (sickdays.LOCKER_WORKOUT, sickdays.LOCKER_ALARM))
    _add(paths, date(2026, 10, 21), (sickdays.LOCKER_DIET,))
    sickdays.remove_sick_day(date(2026, 10, 21), paths=paths, now=TODAY)
    _add(paths, date(2026, 10, 22))
    sickdays.set_kept_lockers(
        date(2026, 10, 22), [sickdays.LOCKER_LEETCODE], paths=paths, now=TODAY
    )
    return paths.log


def write_python(out: Path) -> None:
    """A Python pool for the Dart reader, then the legacy shapes by hand."""
    with tempfile.TemporaryDirectory() as tmp:
        paths = Paths.under(Path(tmp))
        _add(
            paths,
            date(2026, 10, 20),
            (sickdays.LOCKER_LEETCODE, sickdays.LOCKER_WORKOUT),
        )
        _add(paths, date(2026, 10, 22))
        sickdays.set_kept_lockers(
            date(2026, 10, 22), [sickdays.LOCKER_ALARM], paths=paths, now=TODAY
        )
        _add(paths, date(2026, 10, 23))
        for day in (24, 25, 26):
            _add(paths, date(2026, 10, day), (sickdays.LOCKER_ALARM,))
        log = json.loads(paths.log.read_text(encoding="utf-8"))
    fields = log["2026-10-24"]["fields"]
    del fields["keep"]  # a 0.1.0 record: keep nothing
    fields = log["2026-10-25"]["fields"]
    re_add = Hlc.new_tick("old-client", Hlc.from_str(fields["keep"][1])).to_str()
    fields["state"] = ["sick", re_add]  # a 0.1.0 re-add over a 0.2.0 keep: stale
    fields["actor"] = ["old-client", re_add]
    log["2026-10-26"]["fields"]["keep"][0] = "alarm"  # malformed: keep all
    out.write_text(json.dumps(log), encoding="utf-8")


def reading(pool: Path, days: list[date]) -> dict[str, object]:
    """Every per-day verdict a gate relies on."""
    return {
        d.isoformat(): {
            "sick": sickdays.is_sick_day(d, log_path=pool),
            "kept": sorted(sickdays.kept_lockers(d, log_path=pool)),
            "stands_down": {
                locker: sickdays.stands_down(locker, d, log_path=pool)
                for locker in sickdays.LOCKERS
            },
        }
        for d in days
    } | {"sick_days": sorted(d.isoformat() for d in sickdays.sick_days(log_path=pool))}


def wire_problems(pool: Path) -> list[str]:
    """Wire-format slips in a Dart-written pool (empty when clean)."""
    problems = []
    for iso, record in json.loads(pool.read_text(encoding="utf-8")).items():
        fields = record["fields"]
        keep = fields.get("keep")
        if keep is None:
            problems.append(f"{iso}: no keep field")
            continue
        if keep[0] != sorted(set(keep[0])):
            problems.append(f"{iso}: keep {keep[0]} not sorted/deduplicated")
        if record["deleted"]:
            problems.append(f"{iso}: tombstoned")
        state, actor = fields["state"][1], fields["actor"][1]
        if iso in KEEP_EDITED:
            if not (keep[1] == actor and Hlc.from_str(keep[1]) > Hlc.from_str(state)):
                problems.append(f"{iso}: keep-only edit re-stamped state")
        elif len({state, actor, keep[1]}) != 1:
            problems.append(f"{iso}: mark/clear fields carry mixed ticks")
    return problems


def _compare(dart: object, python: object) -> int:
    sys.stdout.write(f"dart:   {json.dumps(dart)}\npython: {json.dumps(python)}\n")
    if dart != python:
        sys.stderr.write("MISMATCH: Dart and Python read different pools\n")
        return 1
    sys.stdout.write("OK: Dart and Python agree\n")
    return 0


def check_dart(dart_pool: Path) -> int:
    """Compare the Dart-written fixture with the Python oracle."""
    with tempfile.TemporaryDirectory() as tmp:
        python = reading(dart_oracle(Path(tmp)), DART_DAYS)
    problems = wire_problems(dart_pool)
    if problems:
        sys.stderr.write("MISMATCH: " + "; ".join(problems) + "\n")
        return 1
    return _compare(reading(dart_pool, DART_DAYS), python)


def check_read(python_pool: Path, dart_reading: Path) -> int:
    """Compare the Dart reader's verdicts on a Python pool with Python's."""
    dart = json.loads(dart_reading.read_text(encoding="utf-8"))
    return _compare(dart, reading(python_pool, PY_DAYS))


def main(argv: list[str]) -> int:
    """Dispatch ``dart`` / ``write`` / ``read`` (see the module docstring)."""
    match argv[1:]:
        case ["dart", dart_pool]:
            return check_dart(Path(dart_pool))
        case ["write", out]:
            write_python(Path(out))
            return 0
        case ["read", python_pool, dart_reading]:
            return check_read(Path(python_pool), Path(dart_reading))
        case _:
            sys.stderr.write(USAGE)
            return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
