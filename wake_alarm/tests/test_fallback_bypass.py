"""A bypass on the phone rings the PC, outside every other rule (2026-11-22).

kuhy paused WakeAlarm from the launcher mid-ring twice and went back to
sleep. The phone now publishes a ``bypass`` event; the PC rings for 30
minutes from it, ignoring the window, a started session, a final reason
and the day's own cap, until a newer ``dismissed`` arrives.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from wake_alarm._enforcement_payload import EnforcementView
from wake_alarm._enforcement_records import PhoneEvent
from wake_alarm._fallback_latch import Latch
from wake_alarm._fallback_policy import (
    BYPASS,
    BYPASS_CLEARED,
    CAP,
    ESCAPE,
    FREE_DAY,
    OUTSIDE_WINDOW,
    SESSION_STARTED,
    SICK_DAY,
    Facts,
    bypass_stop_reason,
    decide,
    needs_facts,
)

A = datetime(2026, 11, 22, 7, 0).astimezone()
DAY = "2026-11-22"


def _at(minutes: float) -> datetime:
    return A + timedelta(minutes=minutes)


def _facts(minutes: float, bypass_minutes: float | None, **overrides: object) -> Facts:
    bypass_at = None if bypass_minutes is None else _at(bypass_minutes)
    fields: dict[str, object] = {"free_day": False, **overrides}
    return Facts(now=_at(minutes), alarm_at=A, bypass_at=bypass_at, **fields)  # type: ignore[arg-type]


def _capped_latch() -> Latch:
    return Latch(
        date=DAY,
        started_at=_at(2).isoformat(),
        stopped_at=_at(32).isoformat(),
        stop_reason=CAP,
    )


class TestDecide:
    def test_a_bypass_rings_over_a_started_session_and_a_used_cap(self) -> None:
        facts = _facts(
            50,
            45,
            session_started=True,
            settled=SESSION_STARTED,
            latch=_capped_latch(),
            ring_started=True,
        )
        assert decide(facts).ring
        assert decide(facts).reason == BYPASS

    def test_a_bypass_rings_at_half_past_ten_outside_the_window(self) -> None:
        assert decide(_facts(210, 205)).reason == BYPASS

    def test_thirty_minutes_after_the_bypass_it_is_quiet(self) -> None:
        decision = decide(_facts(240, 210, session_started=True))
        assert not decision.ring
        assert decision.reason == OUTSIDE_WINDOW

    def test_no_bypass_outside_the_window_stays_quiet(self) -> None:
        assert decide(_facts(210, None)).reason == OUTSIDE_WINDOW

    @pytest.mark.parametrize(
        ("overrides", "reason"),
        [({"free_day": True}, FREE_DAY), ({"sick_day": True}, SICK_DAY)],
    )
    def test_free_and_sick_days_never_ring(
        self, overrides: dict[str, object], reason: str
    ) -> None:
        decision = decide(_facts(50, 45, **overrides))
        assert not decision.ring
        assert decision.reason == reason


class TestStop:
    def test_keeps_ringing_while_the_bypass_stands(self) -> None:
        assert bypass_stop_reason(_facts(50, 45, session_started=True)) is None

    def test_a_newer_dismiss_clears_it(self) -> None:
        assert bypass_stop_reason(_facts(50, None)) == BYPASS_CLEARED

    def test_the_cap_is_thirty_minutes_from_the_bypass(self) -> None:
        assert bypass_stop_reason(_facts(74.9, 45)) is None
        assert bypass_stop_reason(_facts(75, 45)) == CAP

    def test_an_escape_or_a_day_off_stops_it(self) -> None:
        assert bypass_stop_reason(_facts(50, 45, escaped=True)) == ESCAPE
        assert bypass_stop_reason(_facts(50, 45, free_day=True)) == FREE_DAY


class TestNeedsFacts:
    def test_the_bypass_watch_runs_four_hours_past_the_alarm(self) -> None:
        assert needs_facts(_at(239), A, None)
        assert not needs_facts(_at(240), A, None)
        assert not needs_facts(_at(-6), A, None)


def _event(kind: str, at: str, **data: object) -> PhoneEvent:
    return PhoneEvent(at=at, kind=kind, data=dict(data))


class TestView:
    def test_the_newest_bypass_of_the_day(self) -> None:
        view = EnforcementView(
            phone_events=(
                _event(
                    "bypass", "2026-11-22T07:20:00+01:00", cause="suspended", date=DAY
                ),
                _event(
                    "bypass", "2026-11-22T07:10:00+01:00", cause="ring_killed", date=DAY
                ),
                _event(
                    "bypass",
                    "2026-11-21T07:10:00+01:00",
                    cause="suspended",
                    date="2026-11-21",
                ),
            ),
        )
        assert view.bypass_on(DAY) == datetime.fromisoformat(
            "2026-11-22T07:20:00+01:00"
        )

    def test_a_later_dismiss_clears_it(self) -> None:
        view = EnforcementView(
            phone_events=(
                _event("dismissed", "2026-11-22T07:30:00+01:00"),
                _event(
                    "bypass", "2026-11-22T07:20:00+01:00", cause="suspended", date=DAY
                ),
            ),
        )
        assert view.bypass_on(DAY) is None

    def test_an_earlier_dismiss_does_not(self) -> None:
        view = EnforcementView(
            phone_events=(
                _event(
                    "bypass", "2026-11-22T07:40:00+01:00", cause="suspended", date=DAY
                ),
                _event("dismissed", "2026-11-22T07:30:00+01:00"),
            ),
        )
        assert view.bypass_on(DAY) is not None

    def test_no_bypass_today(self) -> None:
        assert EnforcementView().bypass_on(DAY) is None
