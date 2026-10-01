"""Where the daily audit's evidence comes from -- read-only, all of it.

* PC events: every ``events.jsonl*`` line (the live file rotates at 5 MB)
  that carries a top-level ``event`` key -- the named events only, or the
  timeline would be hundreds of lines of routine sync chatter.
* Boots: ``journalctl --list-boots -o json``.
* Resumes: kernel ``Waking up from system sleep state`` lines, read with
  ``_TRANSPORT=kernel`` and a time range -- ``-k`` would cover only the
  current boot.

Every ``journalctl`` call goes through ``_run``, the seam the suite replaces.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
import json
import subprocess
from typing import TYPE_CHECKING

from wake_alarm._constants import LOG_JSONL_FILE

if TYPE_CHECKING:
    from datetime import date

_RESUME_PATTERN = "Waking up from system sleep state"
_USEC = 1_000_000


@dataclass(frozen=True)
class PcEvent:
    """One named line of ``events.jsonl``."""

    at: datetime
    event: str
    message: str
    fields: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class Up:
    """The PC became usable: a boot, or a resume from sleep."""

    at: datetime
    kind: str


# The phone judges up to this many past mornings on a boot/watchdog check.
STICK_CATCH_UP_DAYS = 5


def _midnight(day: date) -> datetime:
    """Local midnight starting ``day``."""
    return datetime.combine(day, datetime.min.time()).astimezone()


def audit_window(day: date) -> tuple[datetime, datetime]:
    """PC evidence: from the start of the day before to the end of ``day``.

    The RTC is re-armed every 15 min, so the first ``rtc_armed`` for ``day``
    is logged any time after the previous morning's wake instant.
    """
    start = _midnight(day)
    return start - timedelta(days=1), start + timedelta(days=1)


def phone_window(day: date) -> tuple[datetime, datetime]:
    """Phone evidence: also the days after, when a late check judged ``day``."""
    start, end = audit_window(day)
    return start, end + timedelta(days=STICK_CATCH_UP_DAYS)


def timeline_window(day: date) -> tuple[datetime, datetime]:
    """What the timeline shows: ``day`` and the evening before."""
    start = _midnight(day)
    return start - timedelta(hours=6), start + timedelta(days=1)


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    """Run ``cmd``; the seam tests replace."""
    return subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=60)


def _journal(cmd: list[str]) -> str:
    """``cmd``'s stdout, or ``""`` when journalctl is missing or failed."""
    try:
        result = _run(cmd)
    except OSError, subprocess.SubprocessError:
        return ""
    return result.stdout if result.returncode == 0 else ""


def _pc_line(line: str) -> tuple[datetime, PcEvent | None] | None:
    """One JSONL line: its instant, and the named event it carries (if any)."""
    try:
        raw = json.loads(line)
        at = datetime.fromisoformat(str(raw.get("ts") or "")).astimezone()
    except ValueError, AttributeError:
        return None
    if not isinstance(raw.get("event"), str):
        return at, None
    fields = raw.get("fields")
    return at, PcEvent(
        at=at,
        event=raw["event"],
        message=str(raw.get("msg") or ""),
        fields=dict(fields) if isinstance(fields, dict) else {},
    )


def read_pc_log(day: date) -> tuple[list[PcEvent], list[datetime]]:
    """Inside :func:`audit_window`: named events, and when anything was logged.

    The second list proves the PC was running even when nothing named
    happened (the trigger and the sync reader log routinely).
    """
    start, end = audit_window(day)
    named: list[PcEvent] = []
    seen: list[datetime] = []
    for path in sorted(LOG_JSONL_FILE.parent.glob(LOG_JSONL_FILE.name + "*")):
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            parsed = _pc_line(line)
            if parsed is None or not start <= parsed[0] < end:
                continue
            seen.append(parsed[0])
            if parsed[1] is not None:
                named.append(parsed[1])
    return sorted(named, key=lambda e: e.at), sorted(seen)


def boots(day: date) -> list[Up]:
    """Boots that started inside :func:`audit_window`."""
    start, end = audit_window(day)
    try:
        listed = json.loads(
            _journal(["journalctl", "--list-boots", "-o", "json", "--no-pager"]) or "[]"
        )
    except ValueError:
        return []
    ups: list[Up] = []
    for boot in listed if isinstance(listed, list) else []:
        first = boot.get("first_entry") if isinstance(boot, dict) else None
        if isinstance(first, int):
            at = datetime.fromtimestamp(first / _USEC, tz=UTC).astimezone()
            if start <= at < end:
                ups.append(Up(at=at, kind="boot"))
    return ups


def resumes(day: date) -> list[Up]:
    """Kernel wake-from-sleep lines inside :func:`audit_window`."""
    start, end = audit_window(day)
    out = _journal(
        [
            "journalctl",
            "_TRANSPORT=kernel",
            "--since",
            start.strftime("%Y-%m-%d %H:%M:%S"),
            "--until",
            end.strftime("%Y-%m-%d %H:%M:%S"),
            "-g",
            _RESUME_PATTERN,
            "-o",
            "json",
            "--no-pager",
        ]
    )
    ups: list[Up] = []
    for line in out.splitlines():
        try:
            entry = json.loads(line)
            stamp = int(entry["__REALTIME_TIMESTAMP"])
        except ValueError, KeyError, TypeError:
            continue
        message = str(entry.get("MESSAGE") or "")
        state = message.rsplit(" ", 1)[-1] if message else "?"
        at = datetime.fromtimestamp(stamp / _USEC, tz=UTC).astimezone()
        ups.append(Up(at=at, kind=f"resume {state}"))
    return ups
