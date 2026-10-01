"""The fallback alarm's table, row by row and at every boundary."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from wake_alarm._fallback_latch import Latch
from wake_alarm._fallback_policy import (
    CAP,
    ESCAPE,
    FREE_DAY,
    NO_SESSION,
    OUTSIDE_WINDOW,
    PHONE_SILENT,
    SESSION_STARTED,
    WAITING,
    Decision,
    Facts,
    alarm_instant,
    decide,
    is_capped,
    needs_facts,
    stop_reason,
)
from wake_alarm._sync import Alarm

DAY = date(2026, 10, 1)
A = datetime(2026, 10, 1, 7, 0).astimezone()


def _at(minutes: float) -> datetime:
    return A + timedelta(minutes=minutes)


def _facts(minutes: float, **overrides: object) -> Facts:
    return Facts(now=_at(minutes), alarm_at=A, free_day=False, **overrides)


def _latch(started_minutes: float, **overrides: object) -> Latch:
    return Latch(
        date=DAY.isoformat(), started_at=_at(started_minutes).isoformat(), **overrides
    )


class TestAlarmInstant:
    def test_earlier_alarm_is_kept(self) -> None:
        assert (
            alarm_instant(Alarm(6, 30, "remote"), DAY)
            == datetime(2026, 10, 1, 6, 30).astimezone()
        )

    def test_later_alarm_is_clamped_to_eight(self) -> None:
        assert alarm_instant(Alarm(13, 0, "cache"), DAY).hour == 8


class TestWindow:
    @pytest.mark.parametrize(
        ("minutes", "inside"),
        [(-5.01, False), (-5, True), (0, True), (44.9, True), (45, False)],
    )
    def test_window_is_a_minus_5_to_a_plus_45(
        self, minutes: float, *, inside: bool
    ) -> None:
        assert needs_facts(_at(minutes), A, None) is inside

    def test_a_ring_already_started_is_judged_outside_the_window(self) -> None:
        assert needs_facts(_at(60), A, _latch(40))

    def test_outside_window_never_rings(self) -> None:
        assert decide(_facts(-10)) == Decision(ring=False, reason=OUTSIDE_WINDOW)
        assert decide(_facts(50)) == Decision(ring=False, reason=OUTSIDE_WINDOW)


class TestTable:
    def test_free_day_wins_over_everything(self) -> None:
        facts = Facts(now=_at(20), alarm_at=A, free_day=True)
        assert decide(facts) == Decision(ring=False, reason=FREE_DAY)

    def test_waiting_before_a_plus_2(self) -> None:
        assert decide(_facts(1.9)) == Decision(ring=False, reason=WAITING)

    def test_phone_silent_from_a_plus_2(self) -> None:
        assert decide(_facts(2)) == Decision(ring=True, reason=PHONE_SILENT)

    def test_ring_started_waits_for_the_session_grace(self) -> None:
        assert decide(_facts(14.9, ring_started=True)) == Decision(
            ring=False, reason=WAITING
        )
        assert decide(_facts(15, ring_started=True)) == Decision(
            ring=True, reason=NO_SESSION
        )

    def test_escape_stops_everything(self) -> None:
        assert decide(_facts(20, escaped=True)) == Decision(ring=False, reason=ESCAPE)

    def test_session_started_stops_everything(self) -> None:
        assert decide(_facts(20, session_started=True)) == Decision(
            ring=False, reason=SESSION_STARTED
        )

    def test_escape_beats_session(self) -> None:
        facts = _facts(20, escaped=True, session_started=True)
        assert decide(facts).reason == ESCAPE

    def test_unreachable_firebase_fails_toward_ringing(self) -> None:
        # The caller models "unreachable" as all-False facts.
        assert decide(_facts(3)).ring

    def test_a_settled_final_reason_holds_when_firebase_goes_quiet(self) -> None:
        assert decide(_facts(20, settled=SESSION_STARTED)) == Decision(
            ring=False, reason=SESSION_STARTED
        )

    def test_a_non_final_settled_value_is_ignored(self) -> None:
        assert decide(_facts(20, settled="phone_silent")).ring


class TestCap:
    def test_thirty_minutes_after_the_first_start(self) -> None:
        assert not is_capped(_facts(31.9, latch=_latch(2)))
        assert is_capped(_facts(32, latch=_latch(2)))
        assert decide(_facts(32, latch=_latch(2))) == Decision(ring=False, reason=CAP)

    def test_a_cap_stop_is_final(self) -> None:
        latch = _latch(2, stopped_at=_at(32).isoformat(), stop_reason=CAP)
        assert is_capped(_facts(3, latch=latch))

    def test_no_latch_or_no_start_is_not_capped(self) -> None:
        assert not is_capped(_facts(40))
        assert not is_capped(_facts(40, latch=Latch(date=DAY.isoformat())))

    def test_a_died_ring_resumes_past_the_window(self) -> None:
        latch = _latch(40)
        assert decide(_facts(50, latch=latch)) == Decision(
            ring=True, reason=PHONE_SILENT
        )
        assert decide(_facts(70, latch=latch)) == Decision(ring=False, reason=CAP)


class TestStopReason:
    def test_keep_ringing_when_the_phone_merely_comes_back(self) -> None:
        assert stop_reason(_facts(5, ring_started=True, latch=_latch(2))) is None

    @pytest.mark.parametrize(
        ("overrides", "reason"),
        [
            ({"escaped": True}, ESCAPE),
            ({"session_started": True}, SESSION_STARTED),
            ({"settled": ESCAPE}, ESCAPE),
        ],
    )
    def test_contract_stop_conditions(
        self, overrides: dict[str, object], reason: str
    ) -> None:
        assert stop_reason(_facts(10, **overrides)) == reason

    def test_free_day_and_cap_stop(self) -> None:
        free = Facts(now=_at(10), alarm_at=A, free_day=True)
        assert stop_reason(free) == FREE_DAY
        assert stop_reason(_facts(33, latch=_latch(2))) == CAP
