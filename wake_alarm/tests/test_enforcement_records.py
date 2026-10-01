"""Single-value builders for the v2 fields."""

from __future__ import annotations

from wake_alarm._enforcement_records import (
    Escape,
    PhoneEvent,
    RingStarted,
    StickState,
    escape_from,
    is_iso_date,
    optional_text,
    parse_instant,
    phone_event_from,
    ring_started_from,
    stick_state_from,
    text,
)


def test_text_never_turns_null_into_none_string() -> None:
    assert text(None) == ""
    assert text(5) == ""
    assert text("x") == "x"
    assert optional_text(None) is None
    assert optional_text("") is None
    assert optional_text("2026-10-01") == "2026-10-01"


def test_is_iso_date() -> None:
    assert is_iso_date("2026-10-01")
    assert not is_iso_date("2026-1-1x")
    assert not is_iso_date("20261001")


def test_parse_instant() -> None:
    aware = parse_instant("2026-10-01T06:00:00+02:00")
    assert aware is not None
    assert aware.utcoffset() is not None
    naive = parse_instant("2026-10-01T06:00:00")
    assert naive is not None
    assert naive.tzinfo is not None
    assert parse_instant("soon") is None


def test_ring_started() -> None:
    assert ring_started_from({"date": "2026-10-01", "at": "x"}) == RingStarted(
        "2026-10-01", "x"
    )
    assert ring_started_from({"date": None, "at": "x"}) is None
    assert ring_started_from("2026-10-01") is None


def test_escape() -> None:
    raw = {"id": "e1", "date": "2026-10-01", "at": None, "reason": "r"}
    assert escape_from(raw) == Escape("e1", "2026-10-01", "", "r")
    assert escape_from({**raw, "id": None}) is None
    assert escape_from({**raw, "date": "yesterday"}) is None
    assert escape_from([raw]) is None


def test_stick_state() -> None:
    raw = {"streak": 2, "locked_through": None, "last_miss": "2026-10-01"}
    assert stick_state_from(raw) == StickState(2, None, "2026-10-01")
    for bad in (True, -1, "2", None):
        assert stick_state_from({**raw, "streak": bad}) is None
    assert stick_state_from(None) is None


def test_phone_event() -> None:
    raw = {"at": "2026-10-01T06:00:00", "kind": "dismissed", "data": {"a": 1}}
    assert phone_event_from(raw) == PhoneEvent(raw["at"], "dismissed", {"a": 1})
    assert phone_event_from({**raw, "data": None}) == PhoneEvent(
        raw["at"], "dismissed", {}
    )
    assert phone_event_from({**raw, "kind": None}) is None
    assert phone_event_from({**raw, "at": ""}) is None
    assert phone_event_from(7) is None
