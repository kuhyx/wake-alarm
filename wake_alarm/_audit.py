"""The daily wake audit: one Markdown report per morning, for Claude to read.

``wake-alarm-audit.timer`` runs it at 11:05; by hand::

    python -m wake_alarm._audit [YYYY-MM-DD] [--dry-run]

It merges the phone's ``phone_events`` with the PC's named ``events.jsonl``
lines, boots and resumes into one timeline, runs the expected-vs-observed
checks (``_audit_checks``) and writes ``INCIDENTS_DIR/<date>.md`` with every
escape and mismatch first, under ``## Flags``. Read-only everywhere except
that one file (and ``audit_written``); ``--dry-run`` prints without writing.
Outside the repo on purpose: the report holds personal data.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime
import sys
from typing import TYPE_CHECKING

import freedays

from wake_alarm._audit_checks import alarm_from_events, flags, run_checks
from wake_alarm._audit_evidence import Check, Evidence, PcSide, PhoneSide
from wake_alarm._audit_sources import (
    boots,
    phone_window,
    read_pc_log,
    resumes,
    timeline_window,
)
from wake_alarm._constants import INCIDENTS_DIR
from wake_alarm._enforcement_payload import EnforcementView, enforcement_view
from wake_alarm._enforcement_records import parse_instant
from wake_alarm._events import emit
from wake_alarm._fallback_policy import alarm_instant
from wake_alarm._logging_setup import configure_logging
from wake_alarm._sick import is_sick
from wake_alarm._sync import get_alarm
from wake_alarm._sync_transport import fetch_firebase_logs
from wake_alarm._workday_penalty import issued_date

if TYPE_CHECKING:
    from wake_alarm._enforcement_records import PhoneEvent

_MARK = {True: "[x]", False: "[ ]", None: "[-]"}


def gather(day: date) -> tuple[Evidence, bool]:
    """Collect the evidence for ``day``; second item is Firebase reachability."""
    published = fetch_firebase_logs()
    view = enforcement_view(published) if published is not None else EnforcementView()
    start, end = phone_window(day)
    pc, pc_seen = read_pc_log(day)
    alarm_at, source = alarm_from_events(pc, day), "PC fallback tick"
    if alarm_at is None:
        alarm_at, source = alarm_instant(get_alarm(), day), "current alarm, assumed"
    phone = [
        e
        for e in view.phone_events
        if (at := parse_instant(e.at)) is not None and start <= at < end
    ]
    evidence = Evidence(
        day=day,
        stick_day=freedays.is_workday(day),
        free_day=freedays.is_free_day(day),
        sick_day=is_sick(day),
        alarm_at=alarm_at,
        alarm_source=source,
        pc_side=PcSide(
            events=pc,
            seen=pc_seen,
            ups=sorted(boots(day) + resumes(day), key=lambda u: u.at),
            penalty_issued=issued_date(),
        ),
        phone_side=PhoneSide(
            events=sorted(phone, key=lambda e: parse_instant(e.at) or start),
            escapes=[e for e in view.escapes if e.date == day.isoformat()],
            ring_started=view.ring_started_on(day.isoformat()),
            stick_state=view.stick_state,
        ),
    )
    return evidence, published is not None


def _shown(ev: Evidence, at: datetime, phone: PhoneEvent | None = None) -> bool:
    """Inside the timeline window, or a late check that judged this day."""
    start, end = timeline_window(ev.day)
    if start <= at < end:
        return True
    return phone is not None and phone.data.get("date") == ev.day.isoformat()


def _row(at: datetime, source: str, name: str, data: dict[str, object]) -> str:
    """One ``| time | source | event | details |`` row."""
    detail = ", ".join(f"{k}={v}" for k, v in sorted(data.items()))
    return f"| {at:%m-%d %H:%M:%S} | {source} | {name} | {detail} |"


def _timeline(ev: Evidence) -> list[str]:
    """The merged rows, oldest first."""
    rows = [
        (pc.at, _row(pc.at, "PC", pc.event, pc.fields))
        for pc in ev.pc
        if _shown(ev, pc.at)
    ]
    for phone in ev.phone:
        at = parse_instant(phone.at)
        if at is not None and _shown(ev, at, phone):
            rows.append((at, _row(at, "phone", phone.kind, phone.data)))
    rows.extend(
        (up.at, _row(up.at, "kernel", up.kind, {}))
        for up in ev.ups
        if _shown(ev, up.at)
    )
    return [row for _, row in sorted(rows, key=lambda r: r[0])]


def render(ev: Evidence, checks: list[Check], *, reachable: bool) -> str:
    """The whole report."""
    kind = (
        "sick day"
        if ev.sick_day
        else "free day"
        if ev.free_day
        else "stick day"
        if ev.stick_day
        else "carrot day"
    )
    lines = [f"# Wake audit {ev.day} ({ev.day:%a}, {kind})", "", "## Flags", ""]
    flagged = flags(ev, checks)
    if not reachable:
        flagged.append("MISMATCH firebase: unreachable -- phone side not audited")
    lines.extend(f"- {line}" for line in flagged or ["none"])
    lines += ["", "## Checks", ""]
    lines.extend(f"- {_MARK[c.ok]} {c.name}: {c.detail}" for c in checks)
    state = ev.stick_state
    lines += [
        "",
        "## Phone state now",
        "",
        f"- stick_state: {state if state is not None else 'not published'}",
        f"- workday_penalty.json issued: {ev.penalty_issued or 'none'}",
        "",
        "## Timeline",
        "",
        "| time | source | event | details |",
        "|---|---|---|---|",
    ]
    lines.extend(_timeline(ev) or ["| | | (nothing recorded) | |"])
    return "\n".join(lines) + "\n"


def write_report(day: date, text: str) -> str:
    """Write the report; returns its path."""
    path = INCIDENTS_DIR / f"{day.isoformat()}.md"
    INCIDENTS_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return str(path)


def main(argv: list[str] | None = None) -> int:
    """Entry point; exit 1 when the report could not be written."""
    parser = argparse.ArgumentParser(description="Audit one wake-up")
    parser.add_argument("day", nargs="?", type=date.fromisoformat, default=None)
    parser.add_argument("--dry-run", action="store_true", help="print, write nothing")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    day = args.day or datetime.now().astimezone().date()
    evidence, reachable = gather(day)
    checks = run_checks(evidence)
    text = render(evidence, checks, reachable=reachable)
    sys.stdout.write(text)
    if args.dry_run:
        return 0
    configure_logging(component="audit")
    try:
        path = write_report(day, text)
    except OSError as exc:
        sys.stderr.write(f"could not write the report: {exc}\n")
        return 1
    emit(
        "audit_written",
        path,
        day=day.isoformat(),
        path=path,
        flags=len(flags(evidence, checks)),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
