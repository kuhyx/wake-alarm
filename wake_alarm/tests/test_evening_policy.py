"""The 21:00 notifications check's rule, as pure functions (2026-11-22)."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from wake_alarm._evening_policy import (
    FREE_TOMORROW,
    NOTIFICATIONS_OFF,
    NOTIFICATIONS_ON,
    OUTSIDE_EVENING,
    SICK_TOMORROW,
    UNREACHABLE,
    EveningFacts,
    decide,
    in_evening,
    needs_fetch,
    stop_reason,
)
from wake_alarm._fallback_latch import Latch
from wake_alarm._fallback_policy import CAP, Decision

DAY = "2026-11-22"
NINE = datetime(2026, 11, 22, 21, 0).astimezone()


def _at(minutes: float) -> datetime:
    return NINE + timedelta(minutes=minutes)


def _latch(started: float, stop: str | None = None) -> Latch:
    return Latch(date=DAY, started_at=_at(started).isoformat(), stop_reason=stop)


@pytest.mark.parametrize("when", [_at(0), _at(59)])
def test_the_21_oclock_hour_is_the_evening(when: datetime) -> None:
    assert in_evening(when)


@pytest.mark.parametrize("when", [_at(-1), _at(60)])
def test_the_minutes_around_it_are_not(when: datetime) -> None:
    assert not in_evening(when)


class TestDecide:
    def test_off_today_rings(self) -> None:
        facts = EveningFacts(now=_at(5), off_since=_at(0))
        assert decide(facts) == Decision(ring=True, reason=NOTIFICATIONS_OFF)

    def test_no_off_event_is_quiet(self) -> None:
        facts = EveningFacts(now=_at(5))
        assert decide(facts) == Decision(ring=False, reason=NOTIFICATIONS_ON)

    def test_outside_the_hour_nothing_starts(self) -> None:
        facts = EveningFacts(now=_at(70), off_since=_at(0))
        assert decide(facts) == Decision(ring=False, reason=OUTSIDE_EVENING)

    @pytest.mark.parametrize("off", [FREE_TOMORROW, SICK_TOMORROW])
    def test_a_free_or_sick_tomorrow_never_rings(self, off: str) -> None:
        facts = EveningFacts(now=_at(5), off_since=_at(0), tomorrow_off=off)
        assert decide(facts) == Decision(ring=False, reason=off)

    def test_unreachable_is_quiet_and_says_so(self) -> None:
        facts = EveningFacts(now=_at(5), reachable=False)
        assert decide(facts) == Decision(ring=False, reason=UNREACHABLE)


class TestCap:
    def test_thirty_minutes_from_the_first_ring_ends_it(self) -> None:
        facts = EveningFacts(now=_at(40), off_since=_at(35), latch=_latch(10))
        assert stop_reason(facts) == CAP
        assert decide(facts) == Decision(ring=False, reason=CAP)

    def test_a_resumed_ring_keeps_its_first_start(self) -> None:
        facts = EveningFacts(now=_at(39), off_since=_at(35), latch=_latch(10, "x"))
        assert stop_reason(facts) is None

    def test_a_latched_cap_holds(self) -> None:
        facts = EveningFacts(now=_at(12), off_since=_at(0), latch=_latch(10, CAP))
        assert stop_reason(facts) == CAP

    def test_a_latch_never_started_caps_nothing(self) -> None:
        facts = EveningFacts(now=_at(50), off_since=_at(0), latch=Latch(date=DAY))
        assert stop_reason(facts) is None

    def test_a_capped_evening_does_not_fetch(self) -> None:
        assert not needs_fetch(EveningFacts(now=_at(45), latch=_latch(10)))
        assert needs_fetch(EveningFacts(now=_at(45), latch=_latch(20)))

    def test_a_free_tomorrow_does_not_fetch(self) -> None:
        assert not needs_fetch(EveningFacts(now=_at(5), tomorrow_off=FREE_TOMORROW))
        assert needs_fetch(EveningFacts(now=_at(5)))


def test_a_ring_past_22_is_judged_by_the_stop_rules_alone() -> None:
    facts = EveningFacts(now=_at(75), off_since=_at(50), latch=_latch(55))
    assert stop_reason(facts) is None
