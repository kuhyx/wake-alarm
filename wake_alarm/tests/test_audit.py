"""The audit report end to end, with every source faked."""

from __future__ import annotations

from datetime import date
import json
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from wake_alarm import _audit, _audit_sources
from wake_alarm._audit import gather, main, render
from wake_alarm._audit_checks import run_checks
from wake_alarm._audit_sources import Up
from wake_alarm._enforcement_records import PhoneEvent
from wake_alarm._sync import Alarm

if TYPE_CHECKING:
    from collections.abc import Generator
from dataclasses import replace

DAY = date(2026, 10, 1)
REASON = "the alarm never rang because the phone rebooted overnight"


def _published() -> list[tuple[str, str]]:
    fields = {
        "phone_events": [
            [
                {"at": "2026-10-01T07:00:02+02:00", "kind": "alarm_fired", "data": {}},
                {"at": "2026-09-20T07:00:02+02:00", "kind": "boot", "data": {}},
                {"at": "soon", "kind": "boot", "data": {}},
            ],
            "h",
        ],
        "escapes": [
            [{"id": "e", "date": "2026-10-01", "at": "x", "reason": REASON}],
            "h",
        ],
    }
    return [("p", json.dumps({"alarm": {"fields": fields}}))]


@pytest.fixture(autouse=True)
def _sources() -> Generator[None]:
    with (
        patch.object(_audit, "fetch_firebase_logs", return_value=_published()),
        patch.object(_audit, "get_alarm", return_value=Alarm(7, 0, "cache")),
        patch.object(_audit, "boots", return_value=[]),
        patch.object(_audit, "resumes", return_value=[]),
    ):
        yield


def test_gather_merges_phone_and_pc() -> None:
    log = _audit_sources.LOG_JSONL_FILE
    log.write_text(
        json.dumps(
            {
                "ts": "2026-10-01T06:55:00+0200",
                "event": "fallback_tick",
                "fields": {"alarm": "2026-10-01T07:00:00+02:00"},
            }
        )
    )
    evidence, reachable = gather(DAY)
    assert reachable
    assert evidence.alarm_source == "PC fallback tick"
    assert [e.kind for e in evidence.phone] == ["alarm_fired"]
    assert [e.id for e in evidence.escapes] == ["e"]


def test_unreachable_firebase_is_flagged() -> None:
    with patch.object(_audit, "fetch_firebase_logs", return_value=None):
        evidence, reachable = gather(DAY)
    assert not reachable
    assert evidence.alarm_source == "current alarm, assumed"
    text = render(evidence, run_checks(evidence), reachable=False)
    assert "firebase: unreachable" in text


def test_render_puts_flags_first_and_builds_a_timeline() -> None:
    with patch.object(_audit, "resumes", return_value=[]):
        evidence, _ = gather(DAY)
    evidence = replace(
        evidence,
        pc_side=replace(evidence.pc_side, ups=[Up(evidence.alarm_at, "resume S4")]),
    )
    text = render(evidence, run_checks(evidence), reachable=True)
    assert text.index("## Flags") < text.index("ESCAPE") < text.index("## Checks")
    assert "| phone | alarm_fired |" in text
    assert "| kernel | resume S4 |" in text
    assert "(Thu, stick day)" in text


def test_an_empty_day_says_so() -> None:
    with patch.object(_audit, "fetch_firebase_logs", return_value=[]):
        evidence, _ = gather(date(2026, 10, 3))
    text = render(evidence, [], reachable=True)
    assert "- none" in text
    assert "(nothing recorded)" in text
    assert "carrot day" in text
    with patch.object(_audit.freedays, "is_free_day", return_value=True):
        evidence, _ = gather(date(2026, 10, 3))
    assert "free day" in render(evidence, [], reachable=True)


def test_pc_event_details_are_rendered() -> None:
    log = _audit_sources.LOG_JSONL_FILE
    log.write_text(
        json.dumps(
            {
                "ts": "2026-10-01T07:02:00+0200",
                "event": "ring_backend",
                "fields": {"a": 1},
            }
        )
    )
    evidence, _ = gather(DAY)
    assert "| PC | ring_backend | a=1 |" in render(evidence, [], reachable=True)


class TestCli:
    def test_dry_run_writes_nothing(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert main(["2026-10-01", "--dry-run"]) == 0
        assert "# Wake audit 2026-10-01" in capsys.readouterr().out
        assert not _audit.INCIDENTS_DIR.exists()

    def test_writes_the_report(self) -> None:
        with (
            patch.object(_audit, "configure_logging"),
            patch("sys.argv", ["prog", "2026-10-01"]),
        ):
            assert main() == 0
        report = _audit.INCIDENTS_DIR / "2026-10-01.md"
        assert report.read_text().startswith("# Wake audit 2026-10-01")

    def test_defaults_to_today(self) -> None:
        with patch.object(_audit, "configure_logging"):
            assert main([]) == 0
        assert len(list(_audit.INCIDENTS_DIR.iterdir())) == 1

    def test_unwritable_report_exits_1(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with (
            patch.object(_audit, "configure_logging"),
            patch.object(_audit, "write_report", side_effect=OSError("ro")),
        ):
            assert main(["2026-10-01"]) == 1
        assert "could not write" in capsys.readouterr().err


def test_timeline_skips_an_unparsable_phone_stamp() -> None:
    evidence, _ = gather(DAY)
    odd = replace(
        evidence,
        phone_side=replace(
            evidence.phone_side, events=[PhoneEvent("soon", "boot", {})]
        ),
    )
    assert "| phone |" not in render(odd, [], reachable=True)


def test_a_late_check_for_the_day_is_on_its_timeline() -> None:
    fields = {
        "phone_events": [
            [
                {
                    "at": "2026-10-03T09:00:00+02:00",
                    "kind": "stick_check",
                    "data": {
                        "date": "2026-10-01",
                        "verdict": "miss",
                        "trigger": "boot",
                    },
                },
                {"at": "2026-10-03T09:00:01+02:00", "kind": "boot", "data": {}},
            ],
            "h",
        ]
    }
    published = [("p", json.dumps({"alarm": {"fields": fields}}))]
    with patch.object(_audit, "fetch_firebase_logs", return_value=published):
        evidence, _ = gather(DAY)
    text = render(evidence, run_checks(evidence), reachable=True)
    assert "| phone | stick_check |" in text
    assert "| phone | boot |" not in text
    assert "miss caught up on 2026-10-03" in text
