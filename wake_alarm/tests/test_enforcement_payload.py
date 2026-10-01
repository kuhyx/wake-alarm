"""Merging the v2 fields across devices."""

from __future__ import annotations

import json

from wake_alarm._enforcement_payload import (
    EnforcementView,
    enforcement_view,
    is_honoured,
)
from wake_alarm._enforcement_records import Escape

REASON = "the alarm rang at the wrong time because the sync broke again"


def _log(**fields: tuple[object, str]) -> str:
    return json.dumps(
        {"alarm": {"fields": {k: [v, hlc] for k, (v, hlc) in fields.items()}}}
    )


def _escape(ident: str, day: str = "2026-10-01", reason: str = REASON) -> dict:
    return {"id": ident, "date": day, "at": f"{day}T07:00:00", "reason": reason}


def test_empty_and_unparsable_logs_give_an_empty_view() -> None:
    view = enforcement_view([("a", "{bad"), ("b", "[]"), ("c", _log())])
    assert view == EnforcementView()
    assert not view.ring_started_on("2026-10-01")
    assert view.escape_for("2026-10-01") is None


def test_newest_hlc_wins_for_ring_started_and_stick_state() -> None:
    old = _log(
        ring_started=({"date": "2026-09-30", "at": "x"}, "2026-09-30T05:00:00Z-0-a"),
        stick_state=({"streak": 1}, "2026-09-30T05:00:00Z-0-a"),
    )
    new = _log(
        ring_started=({"date": "2026-10-01", "at": "y"}, "2026-10-01T05:00:00Z-0-b"),
        stick_state=({"streak": 0, "last_miss": None}, "2026-10-01T05:00:00Z-0-b"),
        phone_events=("not a list", "2026-10-01T05:00:00Z-0-b"),
    )
    view = enforcement_view(
        [("a", old), ("b", new), ("c", _log(ring_started=(1, "z")))]
    )
    assert view.ring_started_on("2026-10-01")
    assert view.stick_state is not None
    assert view.stick_state.streak == 0


def test_escapes_and_events_are_a_union_deduped() -> None:
    event = {"at": "2026-10-01T06:00:00", "kind": "boot", "data": {}}
    a = _log(
        escapes=([_escape("e1"), _escape("e2"), "junk"], "2026-10-01T06:00:00Z-0-a"),
        phone_events=([event], "2026-10-01T06:00:00Z-0-a"),
    )
    b = _log(
        escapes=([_escape("e1")], "2026-10-01T05:00:00Z-0-b"),
        phone_events=([event, {"kind": "x"}], "2026-10-01T05:00:00Z-0-b"),
    )
    view = enforcement_view([("b", b), ("a", a)])
    assert [e.id for e in view.escapes] == ["e1", "e2"]
    assert len(view.phone_events) == 1


def test_only_honoured_escapes_count() -> None:
    raw = _log(
        escapes=(
            [
                _escape("short", reason="too short"),
                _escape("late", day="2026-10-16"),
                _escape("ok", day="2026-10-15"),
            ],
            "h",
        )
    )
    view = enforcement_view([("a", raw)])
    assert [e.id for e in view.honoured_escapes()] == ["ok"]
    assert view.escaped_dates() == frozenset({"2026-10-15"})
    assert view.escape_for("2026-10-16") is None
    assert view.escape_for("2026-10-15") is not None


def test_is_honoured_rejects_a_bad_date() -> None:
    assert not is_honoured(Escape("x", "someday", "", REASON))
    assert not is_honoured(Escape("x", "2026-10-01", "", " " * 50))
