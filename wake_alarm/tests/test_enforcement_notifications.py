"""``EnforcementView.notifications_off_since``: the 21:00 check's input."""

from __future__ import annotations

from datetime import datetime

from wake_alarm._enforcement_payload import EnforcementView
from wake_alarm._enforcement_records import PhoneEvent

DAY = "2026-11-22"


def _notif(hour: int, minute: int, enabled: object, day: int = 22) -> PhoneEvent:
    at = datetime(2026, 11, day, hour, minute).astimezone().isoformat()
    return PhoneEvent(at=at, kind="notifications", data={"enabled": enabled})


def _view(*events: PhoneEvent) -> EnforcementView:
    return EnforcementView(phone_events=events)


def test_no_event_today_is_none() -> None:
    assert _view().notifications_off_since(DAY) is None


def test_the_newest_event_saying_off_is_returned() -> None:
    view = _view(_notif(15, 0, enabled=True), _notif(21, 0, enabled=False))
    assert (
        view.notifications_off_since(DAY) == datetime(2026, 11, 22, 21, 0).astimezone()
    )


def test_a_newer_event_saying_on_clears_it() -> None:
    view = _view(_notif(21, 5, enabled=True), _notif(21, 0, enabled=False))
    assert view.notifications_off_since(DAY) is None


def test_yesterdays_off_does_not_count_today() -> None:
    view = _view(_notif(21, 0, enabled=False, day=21))
    assert view.notifications_off_since(DAY) is None


def test_a_malformed_newer_event_neither_starts_nor_silences() -> None:
    view = _view(
        _notif(21, 0, enabled=False),
        _notif(21, 5, enabled="true"),
        _notif(21, 6, enabled=None),
    )
    assert (
        view.notifications_off_since(DAY) == datetime(2026, 11, 22, 21, 0).astimezone()
    )
    assert _view(_notif(21, 6, enabled=0)).notifications_off_since(DAY) is None


def test_other_kinds_and_undatable_events_are_ignored() -> None:
    view = _view(
        PhoneEvent(at="nope", kind="notifications", data={"enabled": False}),
        PhoneEvent(
            at=datetime(2026, 11, 22, 21, 0).astimezone().isoformat(),
            kind="bypass",
            data={"enabled": False},
        ),
    )
    assert view.notifications_off_since(DAY) is None
