"""Expected-vs-observed checks, one scenario at a time."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta

import pytest

from wake_alarm._audit_checks import (
    alarm_from_events,
    check_alarm,
    check_fallback_stop,
    check_lockdown,
    check_penalty,
    check_ring,
    check_rtc,
    check_up_by_alarm,
    flags,
    run_checks,
)
from wake_alarm._audit_evidence import Evidence, PcSide, PhoneSide
from wake_alarm._audit_sources import PcEvent, Up
from wake_alarm._enforcement_records import Escape, PhoneEvent, StickState

DAY = date(2026, 10, 1)  # a Thursday: stick day
A = datetime(2026, 10, 1, 7, 0).astimezone()
REASON = "the alarm never rang because the phone rebooted overnight"


def _pc(minutes: float, event: str, **fields: object) -> PcEvent:
    return PcEvent(A + timedelta(minutes=minutes), event, "", dict(fields))


def _phone(minutes: float, kind: str, **data: object) -> PhoneEvent:
    return PhoneEvent((A + timedelta(minutes=minutes)).isoformat(), kind, dict(data))


_PC_KEYS = {
    "pc": "events",
    "pc_seen": "seen",
    "ups": "ups",
    "penalty_issued": "penalty_issued",
}
_PHONE_KEYS = {
    "phone": "events",
    "escapes": "escapes",
    "ring_started": "ring_started",
    "stick_state": "stick_state",
}


def _ev(**overrides: object) -> Evidence:
    """Evidence for a stick-day morning, with flat names for either side."""
    pc = {_PC_KEYS[k]: overrides.pop(k) for k in list(overrides) if k in _PC_KEYS}
    phone = {
        _PHONE_KEYS[k]: overrides.pop(k) for k in list(overrides) if k in _PHONE_KEYS
    }
    base = Evidence(
        day=DAY,
        stick_day=True,
        free_day=False,
        alarm_at=A,
        alarm_source="t",
        pc_side=PcSide(**pc),
        phone_side=PhoneSide(**phone),
    )
    return replace(base, **overrides)


ESCAPE = Escape("e", DAY.isoformat(), "2026-10-01T07:30:00", REASON)


def test_alarm_from_events() -> None:
    events = [
        _pc(-5, "fallback_tick", alarm="2026-09-30T07:00:00+02:00"),
        _pc(-5, "fallback_tick", alarm=7),
        _pc(-5, "fallback_tick", alarm="nonsense"),
        _pc(-5, "fallback_tick", alarm=A.isoformat()),
    ]
    assert alarm_from_events(events, DAY) == A
    assert alarm_from_events([], DAY) is None


def test_alarm_known() -> None:
    assert check_alarm(_ev()).ok
    assert check_alarm(_ev(alarm_at=None)).ok is False


def test_rtc_armed() -> None:
    assert check_rtc(_ev(stick_day=False)).ok is None
    assert check_rtc(_ev()).ok is False
    armed = _pc(-600, "rtc_armed", target_date=DAY.isoformat(), wake_at="06:50")
    assert check_rtc(_ev(pc=[armed])).ok


def test_up_by_alarm() -> None:
    assert check_up_by_alarm(_ev(free_day=True)).ok is None
    assert check_up_by_alarm(_ev()).ok is False
    resumed = Up(A - timedelta(minutes=9), "resume S4")
    assert check_up_by_alarm(_ev(ups=[resumed])).ok
    late = Up(A + timedelta(minutes=9), "boot")
    assert check_up_by_alarm(_ev(ups=[late])).ok is False
    assert check_up_by_alarm(_ev(pc_seen=[A - timedelta(minutes=3)])).ok


def test_something_rang() -> None:
    assert check_ring(_ev(free_day=True)).ok is None
    assert check_ring(_ev()).ok is False
    assert check_ring(_ev(ring_started=True)).detail == "phone"
    assert check_ring(_ev(phone=[_phone(0, "alarm_fired")])).ok
    both = _ev(ring_started=True, pc=[_pc(2, "fallback_ring_start")])
    assert check_ring(both).detail == "phone + PC fallback"


def test_fallback_stop() -> None:
    assert check_fallback_stop(_ev()).ok is None
    start = _pc(2, "fallback_ring_start")
    assert check_fallback_stop(_ev(pc=[start])).ok is False
    died = _pc(5, "fallback_ring_stop", stop_reason="terminated")
    assert check_fallback_stop(_ev(pc=[start, died])).ok is False
    good = _pc(9, "fallback_ring_stop", stop_reason="session_started")
    assert check_fallback_stop(_ev(pc=[start, good])).ok


def test_penalty() -> None:
    day = DAY.isoformat()
    assert check_penalty(_ev(escapes=[ESCAPE], penalty_issued=day)).ok is False
    assert check_penalty(_ev(escapes=[ESCAPE])).ok
    assert check_penalty(_ev(stick_day=False)).ok is None
    missed = StickState(1, "2026-10-02", day)
    assert check_penalty(_ev(stick_state=missed)).ok is False
    written = _pc(16, "penalty_written")
    assert check_penalty(_ev(stick_state=missed, pc=[written])).detail == (
        "penalty written"
    )
    assert check_penalty(_ev()).detail == "no miss, no penalty"


class TestLockdown:
    missed = StickState(1, "2026-10-02", DAY.isoformat())
    sent = _phone(15, "lockdown_sent", until="2026-10-02", streak=1)

    def test_no_lockdown(self) -> None:
        assert check_lockdown(_ev()).ok is None

    def test_consistent(self) -> None:
        assert check_lockdown(_ev(stick_state=self.missed, phone=[self.sent])).ok

    @pytest.mark.parametrize(
        "evidence",
        [
            {"stick_state": missed},
            {
                "stick_state": StickState(1, "2026-10-03", DAY.isoformat()),
                "phone": [sent],
            },
            {"phone": [sent]},
            {"phone": [sent], "escapes": [ESCAPE]},
        ],
    )
    def test_mismatches(self, evidence: dict[str, object]) -> None:
        assert check_lockdown(_ev(**evidence)).ok is False

    def test_escape_with_lift_is_fine(self) -> None:
        lifted = [self.sent, _phone(31, "lift_sent")]
        assert check_lockdown(_ev(phone=lifted, escapes=[ESCAPE])).ok

    def test_other_days_and_bad_stamps_are_ignored(self) -> None:
        other = PhoneEvent("2026-09-30T07:15:00", "lockdown_sent", {})
        bad = PhoneEvent("soon", "lockdown_sent", {})
        assert check_lockdown(_ev(phone=[other, bad])).ok is None


def test_flags_put_escapes_first() -> None:
    ignored = Escape("x", DAY.isoformat(), "", "short")
    ev = _ev(escapes=[ESCAPE, ignored])
    lines = flags(ev, run_checks(ev))
    assert lines[0].startswith("ESCAPE 2026-10-01T07:30:00")
    assert "IGNORED" in lines[1]
    assert lines[2].startswith("MISMATCH")
    assert ESCAPE.reason in lines[0]


def test_only_the_daily_firing_counts_as_the_morning_ring() -> None:
    for reason in ("free_day", "rering"):
        fired = _phone(0, "alarm_fired", reason=reason)
        assert check_ring(_ev(phone=[fired])).ok is False
    assert check_ring(_ev(phone=[_phone(0, "alarm_fired", reason="daily")])).ok
    assert check_ring(_ev(phone=[_phone(0, "ring_screen_opened")])).ok


class TestStickVerdicts:
    """Verdicts are keyed by data.date, the morning judged."""

    def _check(
        self, minutes: float, verdict: str, day: str = "2026-10-01"
    ) -> PhoneEvent:
        return _phone(minutes, "stick_check", trigger="boot", verdict=verdict, date=day)

    def test_a_late_boot_check_judges_the_right_morning(self) -> None:
        two_days_later = self._check(2 * 24 * 60, "miss")
        ev = _ev(phone=[two_days_later])
        assert check_penalty(ev).ok is False  # miss, and the PC wrote none
        assert check_lockdown(ev).detail.startswith("miss caught up on 2026-10-03")

    def test_provisional_and_other_days_are_ignored(self) -> None:
        ev = _ev(
            phone=[self._check(15, "too_early"), self._check(15, "miss", "2026-09-30")]
        )
        assert check_penalty(ev).detail == "no miss, no penalty"
        assert check_lockdown(ev).ok is None

    def test_a_same_day_miss_expects_its_lockdown(self) -> None:
        miss = self._check(15, "miss")
        assert check_lockdown(_ev(phone=[miss])).ok is False
        sent = _phone(15, "lockdown_sent", until="2026-10-02")
        other = _phone(16, "dismissed")
        assert (
            check_lockdown(_ev(phone=[miss, other, sent])).detail == "until 2026-10-02"
        )

    def test_an_unparsable_judging_stamp_counts_as_the_day_itself(self) -> None:
        odd = PhoneEvent(
            "soon", "stick_check", {"date": "2026-10-01", "verdict": "miss"}
        )
        bad_stamp = PhoneEvent("soon", "lockdown_sent", {"until": "x"})
        assert check_lockdown(_ev(phone=[odd, bad_stamp])).ok is False

    def test_a_non_miss_verdict_falls_through(self) -> None:
        ev = _ev(phone=[self._check(15, "dismissed")])
        assert check_penalty(ev).detail == "no miss, no penalty"
