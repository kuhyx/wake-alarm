"""The silent monitor probe runs once, at A - 5, with no graphical session."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from wake_alarm import _ring_probe

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

A = datetime(2026, 11, 23, 7, 0).astimezone()


@pytest.fixture(autouse=True)
def done_file(tmp_path: Path) -> Generator[Path]:
    path = tmp_path / "fresh" / "ring_probe_done"
    with patch.object(_ring_probe, "PROBE_DONE_FILE", path):
        yield path


def _run(minutes: float, *, graphical: bool, started: bool = True) -> str | None:
    with (
        patch.object(_ring_probe, "graphical_session", return_value=(graphical, "why")),
        patch.object(_ring_probe, "_ok", return_value=(started, "out")) as ok,
    ):
        result = _ring_probe.maybe_probe(A + timedelta(minutes=minutes), A)
    _run.calls = ok.call_args_list  # type: ignore[attr-defined]
    return result


def test_it_starts_the_unit_at_a_minus_five_with_no_session(done_file: Path) -> None:
    assert _run(-5, graphical=False) == "started"
    assert _run.calls[0].args[0] == [  # type: ignore[attr-defined]
        "sudo",
        "-n",
        "systemctl",
        "start",
        "wake-alarm-ring-probe.service",
    ]
    assert done_file.exists()


def test_it_runs_only_once(done_file: Path) -> None:
    done_file.parent.mkdir()
    done_file.write_text("x")
    assert _run(-4, graphical=False) is None


@pytest.mark.parametrize("minutes", [-6, 0, 30])
def test_only_in_the_five_minutes_before_the_alarm(minutes: float) -> None:
    assert _run(minutes, graphical=False) is None


def test_it_waits_for_a_morning_with_no_session(done_file: Path) -> None:
    assert _run(-3, graphical=True) == "waiting_for_no_session"
    assert not done_file.exists()


def test_a_refused_start_is_retried_next_morning(done_file: Path) -> None:
    assert _run(-3, graphical=False, started=False) == "failed"
    assert not done_file.exists()
