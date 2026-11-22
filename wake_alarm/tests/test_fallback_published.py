"""``--dry-run --published FILE``: plant the phone's logs without a backend.

The live check of the bypass ring (C8, 2026-11-22) could not see ``ring:
bypass`` from the CLI: there is no test backend to plant a ``bypass`` event
in. The file stands in for ``fetch_firebase_logs()`` -- a dry run only, so
a planted world never rings or writes a latch.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from wake_alarm import _fallback, _fallback_evening, _fallback_observe
from wake_alarm._fallback_latch import read_latch
from wake_alarm._published_file import load_published
from wake_alarm._sync import Alarm

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

DAY = "2026-11-22"


def _alarm_json(*events: dict[str, object]) -> dict[str, object]:
    return {"alarm": {"fields": {"phone_events": [list(events), "h"]}}}


def _bypass(at: str) -> dict[str, object]:
    return {"at": f"{DAY}T{at}+01:00", "kind": "bypass", "data": {"date": DAY}}


def _write(tmp_path: Path, content: object) -> str:
    path = tmp_path / "published.json"
    path.write_text(json.dumps(content), encoding="utf-8")
    return str(path)


@pytest.fixture(autouse=True)
def no_backend() -> Generator[MagicMock]:
    """Alarm 08:00 and a Firebase fetch that must never run."""
    fetch = MagicMock(side_effect=AssertionError("fetched Firebase"))
    with (
        patch.object(_fallback_observe, "get_alarm", return_value=Alarm(8, 0, "c")),
        patch.object(_fallback_observe, "fetch_firebase_logs", fetch),
        patch.object(_fallback_evening, "fetch_firebase_logs", fetch),
    ):
        yield fetch


def _dry_run(path: str, at: str) -> int:
    return _fallback.main(["--dry-run", "--at", f"{DAY}T{at}", "--published", path])


def test_a_planted_bypass_rings_in_a_dry_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write(tmp_path, [["phone", _alarm_json(_bypass("10:15:00"))]])
    assert _dry_run(path, "10:30") == 0
    assert "WOULD RING: bypass" in capsys.readouterr().out
    assert read_latch(DAY) is None


def test_raw_text_is_passed_through_as_is(tmp_path: Path) -> None:
    raw = json.dumps(_alarm_json(_bypass("08:05:00")))
    path = _write(tmp_path, [["phone", raw], ["tablet", {"alarm": {}}]])
    assert load_published(path) == [
        ("phone", raw),
        ("tablet", '{"alarm": {}}'),
    ]


def test_an_evening_dry_run_reads_the_file_too(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    event = {
        "at": f"{DAY}T21:00:00+01:00",
        "kind": "notifications",
        "data": {"enabled": False},
    }
    path = _write(tmp_path, [["phone", _alarm_json(event)]])
    assert _dry_run(path, "21:05") == 0
    assert "firebase=ok" in capsys.readouterr().out


@pytest.mark.parametrize("mode", ["--tick", "--show"])
def test_published_needs_dry_run(tmp_path: Path, mode: str) -> None:
    path = _write(tmp_path, [])
    with pytest.raises(SystemExit) as exc:
        _fallback.main([mode, "--published", path])
    assert exc.value.code == 2


@pytest.mark.parametrize(
    "content",
    [
        {"phone": {}},
        [["phone"]],
        [[1, "{}"]],
        [["phone", 3]],
    ],
)
def test_a_malformed_file_is_refused(tmp_path: Path, content: object) -> None:
    with pytest.raises(SystemExit) as exc:
        _dry_run(_write(tmp_path, content), "08:10")
    assert exc.value.code == 2


def test_a_missing_or_unparsable_file_is_refused(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    for path in (str(bad), str(tmp_path / "absent.json")):
        with pytest.raises(SystemExit) as exc:
            _dry_run(path, "08:10")
        assert exc.value.code == 2
