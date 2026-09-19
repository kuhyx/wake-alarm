"""Selecting the phone's newest morning out of the synced logs."""

from __future__ import annotations

import json

from wake_alarm._session_payload import SessionRecord, newest_session, record_from_json

HLC = "2026-09-19T06:20:00.000Z-0000-phone"


def _session(
    date: str = "2026-09-19", outcome: str = "completed", **extra: object
) -> dict:
    return {
        "date": date,
        "started_at": f"{date}T08:01:00.000",
        "updated_at": f"{date}T08:40:00.000",
        "outcome": outcome,
        "weight_kg": 73.8,
        "energy": 3,
        "re_rings": 1,
        **extra,
    }


def _log(
    history: list[dict] | None = None,
    live: object = None,
    hlc: str = HLC,
    live_hlc: str = HLC,
) -> str:
    fields: dict[str, object] = {}
    if history is not None:
        fields["morning_sessions"] = [history, hlc]
    if live is not None:
        fields["current_session"] = [live, live_hlc]
    return json.dumps({"alarm": {"fields": fields}})


class TestRecordFromJson:
    """One phone session JSON -> one record."""

    def test_maps_the_phone_outcome_and_dates_a_finished_one(self) -> None:
        record = record_from_json(_session(), device_id="p", published_at=1.0)
        assert record == SessionRecord(
            date="2026-09-19",
            outcome="completed",
            started_at="2026-09-19T08:01:00.000",
            finished_at="2026-09-19T08:40:00.000",
            energy=3,
            weight_kg=73.8,
            re_rings=1,
            device_id="p",
            published_at=1.0,
        )

    def test_a_live_session_has_no_finish_and_maps_to_in_progress(self) -> None:
        record = record_from_json(
            _session(outcome="active"), device_id="p", published_at=None
        )
        assert record is not None
        assert record.outcome == "in_progress"
        assert record.finished_at is None
        assert not record.finished

    def test_rejects_every_malformed_shape(self) -> None:
        bad = [
            "text",
            {},
            _session(date=1),
            _session(started_at=None),
            _session(outcome="odd"),
            _session(outcome=3),
        ]
        for value in bad:
            assert record_from_json(value, device_id="p", published_at=None) is None

    def test_optional_numbers_refuse_bools_and_strings(self) -> None:
        record = record_from_json(
            _session(energy=True, weight_kg="73", re_rings=False, updated_at=5),
            device_id="p",
            published_at=None,
        )
        assert record is not None
        assert record.energy is None
        assert record.weight_kg is None
        assert record.re_rings == 0
        assert record.finished_at is None


class TestNewestSession:
    """Ranking across fields and devices."""

    def test_finished_beats_live_on_the_same_date_whatever_the_stamps(self) -> None:
        raw = _log(
            history=[_session()],
            live=_session(outcome="active"),
            hlc="2026-09-19T06:00:00.000Z-0000-phone",
            live_hlc="2026-09-19T09:00:00.000Z-0000-phone",
        )
        record = newest_session([("p", raw)])
        assert record is not None
        assert record.outcome == "completed"

    def test_a_newer_live_date_beats_older_finished_ones(self) -> None:
        raw = _log(
            history=[_session(date="2026-09-18")], live=_session(outcome="active")
        )
        record = newest_session([("p", raw)])
        assert record is not None
        assert (record.date, record.outcome) == ("2026-09-19", "in_progress")

    def test_hlc_then_device_id_break_ties(self) -> None:
        older = _log(history=[_session()], hlc="2026-09-19T06:00:00.000Z-0000-a")
        newer = _log(history=[_session()], hlc="2026-09-19T07:00:00.000Z-0000-b")
        assert newest_session([("a", older), ("b", newer)]).device_id == "b"
        same = _log(history=[_session()])
        assert newest_session([("a", same), ("b", same)]).device_id == "b"

    def test_skips_unusable_logs_and_entries(self) -> None:
        published = [
            ("json", "nope"),
            ("list", "[]"),
            ("empty", _log()),
            ("cleared", _log(live={})),
            ("bad-history", _log(history=[{"date": "2026-09-19"}])),
            (
                "history-not-list",
                json.dumps({"alarm": {"fields": {"morning_sessions": [3, HLC]}}}),
            ),
            ("finished-in-live-slot", _log(live=_session())),
            ("live-in-history", _log(history=[_session(outcome="active")])),
        ]
        assert newest_session(published) is None
        assert (
            newest_session([*published, ("ok", _log(history=[_session()]))]) is not None
        )

    def test_carries_the_stamp_instant(self) -> None:
        record = newest_session([("p", _log(history=[_session()]))])
        assert record is not None
        assert record.published_at is not None
