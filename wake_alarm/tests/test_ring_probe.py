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
# The argv lists the last ``_run`` handed to ``_ok``, newest run only.
CALLS: list[object] = []


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
    CALLS[:] = [call.args[0] for call in ok.call_args_list]
    return result


def test_it_starts_the_unit_at_a_minus_five_with_no_session(done_file: Path) -> None:
    assert _run(-5, graphical=False) == "started"
    assert CALLS[0] == [
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


def test_a_skipped_morning_is_logged_once_a_day() -> None:
    # Without it, a missing ring_probe line at 08:00 cannot tell "kuhy was
    # logged in" from "the probe never ran".
    with patch.object(_ring_probe, "emit_on_change") as emit:
        assert _run(-3, graphical=True) == "waiting_for_no_session"
    emit.assert_called_once_with(
        "ring_probe",
        "2026-11-23|waiting_for_no_session",
        "waiting_for_no_session",
        session="why",
    )
