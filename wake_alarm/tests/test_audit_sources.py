"""The audit's evidence readers, with journalctl faked."""

from __future__ import annotations

from datetime import date, datetime
import json
import logging
import subprocess
from unittest.mock import MagicMock, patch

from wake_alarm import _audit_sources
from wake_alarm._audit_sources import (
    audit_window,
    boots,
    phone_window,
    read_pc_log,
    resumes,
    timeline_window,
)
from wake_alarm._events import emit
from wake_alarm._log_sink import build_handler

# Bound at import, before conftest swaps the seam for a raiser.
REAL_RUN = _audit_sources._run
DAY = date(2026, 10, 1)


def _done(stdout: str, code: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], code, stdout=stdout, stderr="")


def _line(ts: str, **extra: object) -> str:
    return json.dumps({"ts": ts, "msg": "m", **extra})


def _usec(*parts: int) -> int:
    return int(datetime(*parts).astimezone().timestamp() * 1_000_000)


def test_windows() -> None:
    start, end = audit_window(DAY)
    assert start == datetime(2026, 9, 30, 0, 0).astimezone()
    assert end == datetime(2026, 10, 2, 0, 0).astimezone()
    assert phone_window(DAY) == (start, datetime(2026, 10, 7, 0, 0).astimezone())
    assert timeline_window(DAY) == (datetime(2026, 9, 30, 18, 0).astimezone(), end)


def test_pc_log_reads_rotated_files_and_keeps_named_events() -> None:
    live = _audit_sources.LOG_JSONL_FILE
    rotated = live.with_name(live.name + ".1")
    rotated.write_text(
        _line("2026-09-30T21:00:00+0200", event="rtc_armed", fields={"a": 1}) + "\n"
    )
    live.write_text(
        "\n".join(
            [
                _line("2026-10-01T06:50:00+0200"),
                _line("2026-10-01T07:02:00+0200", event="fallback_tick", fields=[1]),
                _line("2026-09-29T07:00:00+0200", event="old"),
                _line("garbage"),
                "not json",
                "[1, 2]",
            ]
        )
    )
    named, seen = read_pc_log(DAY)
    assert [e.event for e in named] == ["rtc_armed", "fallback_tick"]
    assert named[0].fields == {"a": 1}
    assert named[1].fields == {}
    assert len(seen) == 3


def test_pc_log_skips_unreadable_files() -> None:
    _audit_sources.LOG_JSONL_FILE.mkdir()
    assert read_pc_log(DAY) == ([], [])


def test_boots_in_the_window() -> None:
    listed = [
        {"first_entry": _usec(2026, 10, 1, 6, 50)},
        {"first_entry": _usec(2026, 9, 20, 6, 50)},
        {"first_entry": "x"},
        "junk",
    ]
    with patch.object(_audit_sources, "_run", return_value=_done(json.dumps(listed))):
        found = boots(DAY)
    assert [u.kind for u in found] == ["boot"]
    with patch.object(_audit_sources, "_run", return_value=_done("{not json")):
        assert boots(DAY) == []
    with patch.object(_audit_sources, "_run", return_value=_done("", 1)):
        assert boots(DAY) == []
    with patch.object(_audit_sources, "_run", side_effect=OSError("no journal")):
        assert boots(DAY) == []


def test_resumes_from_kernel_lines() -> None:
    lines = [
        json.dumps(
            {
                "__REALTIME_TIMESTAMP": str(_usec(2026, 10, 1, 6, 50)),
                "MESSAGE": "ACPI: PM: Waking up from system sleep state S4",
            }
        ),
        json.dumps({"__REALTIME_TIMESTAMP": str(_usec(2026, 10, 1, 7)), "MESSAGE": ""}),
        json.dumps({"MESSAGE": "no stamp"}),
        "garbage",
    ]
    run = MagicMock(return_value=_done("\n".join(lines)))
    with patch.object(_audit_sources, "_run", run):
        found = resumes(DAY)
    assert [u.kind for u in found] == ["resume S4", "resume ?"]
    cmd = run.call_args.args[0]
    assert "_TRANSPORT=kernel" in cmd
    assert "-k" not in cmd


def test_real_seam() -> None:
    with patch.object(subprocess, "run", return_value=_done("ok")) as run:
        assert REAL_RUN(["journalctl"]).stdout == "ok"
    run.assert_called_once()


def test_what_emit_writes_is_what_the_audit_reads() -> None:
    """The real JSONL writer into the real reader: the `event` key contract."""
    handler = build_handler(_audit_sources.LOG_JSONL_FILE)
    root = logging.getLogger()
    root.addHandler(handler)
    previous = root.level
    root.setLevel(logging.INFO)
    try:
        emit("rtc_armed", "wake at 06:50", target_date="2026-10-01", epoch=5)
    finally:
        root.removeHandler(handler)
        root.setLevel(previous)
        handler.close()
    named, seen = read_pc_log(datetime.now().astimezone().date())
    assert [(e.event, e.fields) for e in named] == [
        ("rtc_armed", {"target_date": "2026-10-01", "epoch": 5})
    ]
    assert len(seen) == 1
