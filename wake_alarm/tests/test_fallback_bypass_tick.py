"""The tick rings for a phone bypass, on its own clock (2026-11-22)."""

from __future__ import annotations

from datetime import datetime, timedelta
import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from wake_alarm import _fallback, _fallback_observe
from wake_alarm._fallback_latch import read_latch
from wake_alarm._fallback_policy import Decision
from wake_alarm._sync import Alarm

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

DAY = "2026-11-22"
A = datetime(2026, 11, 22, 7, 0).astimezone()


def _log(*events: dict[str, object]) -> list[tuple[str, str]]:
    session = {"date": DAY, "started_at": f"{DAY}T07:20:00", "outcome": "active"}
    fields = {
        "current_session": [session, "h"],
        "phone_events": [list(events), "h2"],
    }
    return [("p", json.dumps({"alarm": {"fields": fields}}))]


def _bypass(minutes: float) -> dict[str, object]:
    at = (A + timedelta(minutes=minutes)).isoformat()
    return {"at": at, "kind": "bypass", "data": {"cause": "suspended", "date": DAY}}


def _dismissed(minutes: float) -> dict[str, object]:
    return {"at": (A + timedelta(minutes=minutes)).isoformat(), "kind": "dismissed"}


@pytest.fixture(autouse=True)
def world() -> Generator[MagicMock]:
    with (
        patch.object(_fallback_observe, "get_alarm", return_value=Alarm(7, 0, "c")),
        patch.object(_fallback, "get_alarm", return_value=Alarm(7, 0, "c")),
        patch.object(_fallback, "ensure_pair", return_value=("r", "l")),
        patch.object(_fallback, "_now", return_value=A + timedelta(minutes=215)),
        patch.object(_fallback, "ring") as ring,
    ):

        def fake_ring(poll: Callable[[], str | None], **_: object) -> str:
            return poll() or "still"

        ring.side_effect = fake_ring
        yield ring


def test_a_bypass_rings_at_half_past_ten_until_a_newer_dismiss(
    world: MagicMock,
) -> None:
    with patch.object(
        _fallback_observe,
        "fetch_firebase_logs",
        side_effect=[_log(_bypass(205)), _log(_dismissed(214), _bypass(205))],
    ):
        decision = _fallback.tick(A + timedelta(minutes=210))
    assert decision == Decision(ring=True, reason="bypass")
    world.assert_called_once()
    assert read_latch(DAY) is None


def test_an_unreachable_poll_keeps_ringing(world: MagicMock) -> None:
    with patch.object(
        _fallback_observe, "fetch_firebase_logs", side_effect=[_log(_bypass(205)), None]
    ):
        _fallback.tick(A + timedelta(minutes=210))
    assert world.call_count == 1
    assert world.call_args is not None


def test_dry_run_reports_the_bypass(capsys: pytest.CaptureFixture[str]) -> None:
    with patch.object(
        _fallback_observe, "fetch_firebase_logs", return_value=_log(_bypass(205))
    ):
        _fallback.main(["--dry-run", "--at", (A + timedelta(minutes=210)).isoformat()])
    out = capsys.readouterr().out
    assert "WOULD RING: bypass" in out
    assert "bypass_at=2026-11-22" in out
