"""Sick days stand the PC down: no fallback ring, no RTC wake, no trigger.

The pool is the real ``sickdays`` package writing into ``tmp_path``
(``conftest`` redirects it); only the network sync is stubbed.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
import importlib
import sys
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
import sickdays

from wake_alarm import _fallback, _fallback_observe, _rtc, _sick, _trigger
from wake_alarm._fallback_latch import mark_started
from wake_alarm._fallback_policy import SICK_DAY, Decision, Facts, decide, stop_reason
from wake_alarm._sync import Alarm

if TYPE_CHECKING:
    from collections.abc import Generator

TUESDAY = date(2026, 10, 6)
A = datetime(2026, 10, 6, 7, 0).astimezone()
MONDAY_EVENING = datetime(2026, 10, 5, 22, 0).astimezone()


def mark_sick(day: date) -> None:
    """Put ``day`` in the (redirected) pool; may be in the past."""
    sickdays.import_legacy([day])


def pull_marks_tuesday() -> bool:
    """A sync that brings TUESDAY in from another device."""
    mark_sick(TUESDAY)
    return True


@pytest.fixture
def sync() -> Generator[MagicMock]:
    """The network pull, observed; reports success."""
    with patch("sickdays.sync_quietly", return_value=True) as pulled:
        yield pulled


class TestSickModule:
    def test_reads_the_pool(self) -> None:
        assert not _sick.is_sick(TUESDAY)
        mark_sick(TUESDAY)
        assert _sick.is_sick(TUESDAY)

    def test_synced_pulls_first(self, sync: MagicMock) -> None:
        sync.side_effect = pull_marks_tuesday
        assert _sick.is_sick_synced(TUESDAY)
        sync.assert_called_once_with()

    def test_missing_package_is_never_sick(self) -> None:
        try:
            with patch.dict(sys.modules, {"sickdays": None}):
                reloaded = importlib.reload(_sick)
                assert reloaded._AVAILABLE is False
                assert not reloaded.is_sick(TUESDAY)
                assert not reloaded.sync()
        finally:
            importlib.reload(_sick)
        assert _sick._AVAILABLE is True


class TestFallbackPolicy:
    def test_a_sick_day_never_rings(self) -> None:
        facts = Facts(now=A + timedelta(minutes=20), alarm_at=A, free_day=False)
        assert decide(facts).ring
        sick = Facts(
            now=A + timedelta(minutes=20), alarm_at=A, free_day=False, sick_day=True
        )
        assert decide(sick) == Decision(ring=False, reason=SICK_DAY)
        assert stop_reason(sick) == SICK_DAY


@pytest.fixture
def alarm_seven() -> Generator[None]:
    with (
        patch.object(_fallback_observe, "get_alarm", return_value=Alarm(7, 0, "c")),
        patch.object(_fallback, "get_alarm", return_value=Alarm(7, 0, "c")),
    ):
        yield


@pytest.mark.usefixtures("alarm_seven")
class TestFallback:
    def test_in_window_act_pulls_and_stays_offline(self, sync: MagicMock) -> None:
        sync.side_effect = pull_marks_tuesday
        fetch = MagicMock()
        with patch.object(_fallback_observe, "fetch_firebase_logs", fetch):
            seen = _fallback_observe.observe(A + timedelta(minutes=3), sync=True)
        assert seen.facts.sick_day
        sync.assert_called_once_with()
        fetch.assert_not_called()

    def test_dry_run_never_pulls(self, sync: MagicMock) -> None:
        mark_sick(TUESDAY)
        seen = _fallback_observe.observe(A + timedelta(minutes=3), sync=False)
        assert seen.facts.sick_day
        sync.assert_not_called()

    def test_off_window_tick_never_pulls(self, sync: MagicMock) -> None:
        _fallback_observe.observe(A - timedelta(hours=2), sync=True)
        sync.assert_not_called()

    def test_a_ring_in_progress_stops(self) -> None:
        mark_sick(TUESDAY)
        mark_started(None, day=TUESDAY.isoformat(), now=A, reason="phone_silent")
        with patch.object(_fallback, "ring_now") as ring_now:
            decision = _fallback.tick(A + timedelta(minutes=5))
        assert decision == Decision(ring=False, reason=SICK_DAY)
        ring_now.assert_not_called()
        latch = _fallback.read_latch(TUESDAY.isoformat())
        assert latch is not None
        assert latch.stop_reason == SICK_DAY

    def test_reports_say_sick(self, capsys: pytest.CaptureFixture[str]) -> None:
        mark_sick(TUESDAY)
        _fallback.main(["--dry-run", "--at", "2026-10-06T07:05:00"])
        assert "quiet: sick_day" in capsys.readouterr().out
        with patch.object(_fallback, "_now", return_value=A):
            _fallback.main(["--show"])
        assert "sick_day=True" in capsys.readouterr().out


class TestRtc:
    def test_a_sick_stick_day_is_skipped(self) -> None:
        assert _rtc.plan(MONDAY_EVENING, Alarm(7, 0, "c")).arm
        mark_sick(TUESDAY)
        chosen = _rtc.plan(MONDAY_EVENING, Alarm(7, 0, "c"))
        assert (chosen.arm, chosen.reason) == (False, "sick day")

    def test_arm_pulls_dry_run_does_not(self, sync: MagicMock) -> None:
        sync.side_effect = pull_marks_tuesday
        with (
            patch.object(_rtc, "get_alarm", return_value=Alarm(7, 0, "c")),
            patch.object(_rtc, "_now", return_value=MONDAY_EVENING),
            patch.object(_rtc, "configure_logging"),
            patch.object(_rtc, "cancel_for_sick_day") as retract,
        ):
            assert _rtc.main(["--dry-run"]) == 0
            sync.assert_not_called()
            retract.assert_not_called()
            assert _rtc.main(["--arm"]) == 0  # a skip is not a failure
        sync.assert_called_once_with()
        retract.assert_called_once_with()


def test_the_trigger_skips_a_sick_day() -> None:
    assert _trigger._skip_reason(A) is None
    mark_sick(TUESDAY)
    assert _trigger._skip_reason(A) == "sick day"
