"""The PC rings at 21:00 when the phone's notifications are off (2026-11-22).

Switching off "All WakeAlarm notifications" silences tomorrow's ring and no
device policy can lock that switch, so the phone reports it as a
``notifications`` event and the PC rings in the 21:00 hour until it is back
on, for at most 30 minutes, unless tomorrow is a free or sick day.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from wake_alarm import _fallback, _fallback_evening, _fallback_observe
from wake_alarm._fallback_latch import Latch, read_latch, write_latch
from wake_alarm._fallback_policy import Decision
from wake_alarm._sync import Alarm

if TYPE_CHECKING:
    from collections.abc import Callable, Generator
    from contextlib import AbstractContextManager

DAY = "2026-11-22"
TOMORROW = date(2026, 11, 23)
NINE = datetime(2026, 11, 22, 21, 0).astimezone()
# Taken before the autouse fixture patches the seam.
REAL_NOW = _fallback_evening._now


def _at(minutes: float) -> datetime:
    return NINE + timedelta(minutes=minutes)


def _notif(minutes: float, *, enabled: bool) -> dict[str, object]:
    return {
        "at": _at(minutes).isoformat(),
        "kind": "notifications",
        "data": {"enabled": enabled, "trigger": "evening"},
    }


def _log(*events: dict[str, object]) -> list[tuple[str, str]]:
    fields = {"phone_events": [list(events), "h"]}
    return [("p", json.dumps({"alarm": {"fields": fields}}))]


def _evening_latch() -> Latch | None:
    return read_latch(DAY, _fallback_evening.EVENING_RING_FILE)


@pytest.fixture(autouse=True)
def world() -> Generator[MagicMock]:
    with (
        patch.object(_fallback_observe, "get_alarm", return_value=Alarm(7, 0, "c")),
        patch.object(_fallback_evening, "ensure_pair", return_value=("r", "l")),
        patch.object(_fallback_evening, "_now", return_value=_at(8)),
        patch.object(_fallback_evening, "ring") as ring,
    ):

        def fake_ring(poll: Callable[[], str | None], **_: object) -> str:
            return poll() or "still"

        ring.side_effect = fake_ring
        yield ring


def _fetch(
    *answers: list[tuple[str, str]] | None,
) -> AbstractContextManager[MagicMock]:
    return patch.object(_fallback_evening, "fetch_firebase_logs", side_effect=answers)


def test_off_rings_until_a_newer_event_says_on(world: MagicMock) -> None:
    with _fetch(_log(_notif(0, enabled=False)), _log(_notif(7, enabled=True))):
        decision = _fallback.tick(_at(5))
    assert decision == Decision(ring=True, reason="notifications_off")
    world.assert_called_once()
    latch = _evening_latch()
    assert latch is not None
    assert latch.started_at == _at(5).isoformat()
    assert latch.stop_reason == "notifications_on"
    assert read_latch(DAY) is None


def test_no_event_today_rings_nothing(world: MagicMock) -> None:
    with _fetch(_log()):
        decision = _fallback.tick(_at(5))
    assert decision == Decision(ring=False, reason="notifications_on")
    world.assert_not_called()


def test_an_unreachable_tick_rings_nothing(world: MagicMock) -> None:
    with _fetch(None):
        assert _fallback.tick(_at(5)).reason == "firebase_unreachable"
    world.assert_not_called()


def test_an_unreachable_poll_keeps_ringing() -> None:
    with _fetch(_log(_notif(0, enabled=False)), None):
        _fallback.tick(_at(5))
    latch = _evening_latch()
    assert latch is not None
    assert latch.stop_reason == "still"


def test_a_free_tomorrow_never_rings_or_fetches(world: MagicMock) -> None:
    with (
        patch.object(
            _fallback_evening.freedays, "is_free_day", side_effect=TOMORROW.__eq__
        ),
        _fetch() as fetch,
    ):
        assert _fallback.tick(_at(5)).reason == "free_tomorrow"
    fetch.assert_not_called()
    world.assert_not_called()


def test_a_sick_tomorrow_never_rings(world: MagicMock) -> None:
    with (
        patch.object(_fallback_evening, "alarm_stands_down_synced") as sick,
        _fetch(),
    ):
        sick.side_effect = TOMORROW.__eq__
        assert _fallback.tick(_at(5)).reason == "sick_tomorrow"
    world.assert_not_called()


def test_a_free_today_before_a_workday_still_rings(world: MagicMock) -> None:
    today = NINE.date()
    with (
        patch.object(
            _fallback_evening.freedays, "is_free_day", side_effect=today.__eq__
        ),
        _fetch(_log(_notif(0, enabled=False)), _log(_notif(7, enabled=True))),
    ):
        assert _fallback.tick(_at(5)).ring
    world.assert_called_once()


def test_a_capped_evening_stays_quiet_without_fetching(world: MagicMock) -> None:
    write_latch(
        Latch(date=DAY, started_at=_at(0).isoformat()),
        _fallback_evening.EVENING_RING_FILE,
    )
    with _fetch() as fetch:
        assert _fallback.tick(_at(31)).reason == "cap"
    fetch.assert_not_called()
    world.assert_not_called()
    latch = _evening_latch()
    assert latch is not None
    assert latch.stop_reason == "cap"


def test_the_catch_up_tick_after_22_is_the_morning_path(world: MagicMock) -> None:
    with _fetch() as fetch:
        assert _fallback.tick(_at(90)).reason == "outside_window"
    fetch.assert_not_called()
    world.assert_not_called()


def test_dry_run_reports_and_writes_nothing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with (
        _fetch(_log(_notif(0, enabled=False))),
        patch.object(_fallback_evening, "alarm_stands_down_synced") as synced,
    ):
        _fallback.main(["--dry-run", "--at", _at(5).isoformat()])
    out = capsys.readouterr().out
    assert "WOULD RING: notifications_off" in out
    assert "off_since=2026-11-22 21:00" in out
    synced.assert_not_called()
    assert _evening_latch() is None


def test_dry_run_outside_the_hour_is_the_morning_report(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _fallback.main(["--dry-run", "--at", _at(90).isoformat()])
    assert "quiet: outside_window" in capsys.readouterr().out


def test_the_clock_seam_is_aware_local_now() -> None:
    assert REAL_NOW().tzinfo is not None
