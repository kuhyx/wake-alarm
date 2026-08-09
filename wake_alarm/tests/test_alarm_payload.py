"""Tests for parsing and ranking the alarm payload devices publish.

A misparse here does not raise -- it resolves to the wrong wake-up time --
so the malformed shapes are covered as carefully as the good ones.
"""

from __future__ import annotations

import json

from wake_alarm._alarm_payload import extract_hlc, newest_alarm, parse_log


def _log(hour: object = 7, minute: object = 30, hlc: str = "hlc-1") -> str:
    """Build a crdt_sync log payload shaped like the phone's."""
    return json.dumps(
        {
            "alarm": {
                "fields": {
                    "alarm_hour": [hour, hlc],
                    "alarm_minute": [minute, hlc],
                }
            }
        }
    )


class TestExtractHlc:
    def test_reads_the_stamp(self) -> None:
        """The HLC is element 1 of the (value, HLC) pair."""
        assert extract_hlc(json.loads(_log(hlc="stamp-9")), "alarm_hour") == "stamp-9"

    def test_a_pair_with_no_hlc_reads_as_empty(self) -> None:
        """A one-element pair sorts below every real stamp rather than raising."""
        log = {"alarm": {"fields": {"alarm_hour": [7]}}}

        assert extract_hlc(log, "alarm_hour") == ""

    def test_a_non_string_hlc_reads_as_empty(self) -> None:
        """A numeric stamp is not orderable against real ones; treat as absent."""
        log = {"alarm": {"fields": {"alarm_hour": [7, 12345]}}}

        assert extract_hlc(log, "alarm_hour") == ""

    def test_a_missing_record_reads_as_empty(self) -> None:
        """No alarm record at all is not an error here."""
        assert extract_hlc({}, "alarm_hour") == ""


class TestNewestAlarm:
    def test_no_devices_yields_none(self) -> None:
        """Nothing published is a miss, not a crash."""
        assert newest_alarm([]) is None

    def test_every_device_unusable_yields_none(self) -> None:
        """If no device parses, there is no alarm to return."""
        assert newest_alarm([("a", "{not json"), ("b", "[]")]) is None

    def test_newest_hlc_wins(self) -> None:
        """The device that set the alarm last wins, not the first listed."""
        published = [
            ("old", _log(9, 0, hlc="2026-07-01T10:00:00.000Z-0000-old")),
            ("new", _log(5, 30, hlc="2026-08-09T10:00:00.000Z-0000-new")),
        ]

        assert newest_alarm(published) == (5, 30)

    def test_ranking_is_independent_of_listing_order(self) -> None:
        """Reversing the input must not change the winner."""
        published = [
            ("new", _log(5, 30, hlc="2026-08-09T10:00:00.000Z-0000-new")),
            ("old", _log(9, 0, hlc="2026-07-01T10:00:00.000Z-0000-old")),
        ]

        assert newest_alarm(published) == (5, 30)
        assert newest_alarm(list(reversed(published))) == (5, 30)

    def test_an_exact_hlc_tie_breaks_on_device_id(self) -> None:
        """Two devices stamped identically must not alternate between ticks."""
        published = [
            ("aaa", _log(6, 0, hlc="same")),
            ("zzz", _log(8, 0, hlc="same")),
        ]

        assert newest_alarm(published) == (8, 0)
        assert newest_alarm(list(reversed(published))) == (8, 0)

    def test_an_unusable_device_is_skipped_not_fatal(self) -> None:
        """A corrupt publisher must not shadow a healthy one."""
        published = [("broken", "{not json"), ("good", _log(7, 20))]

        assert newest_alarm(published) == (7, 20)

    def test_an_out_of_range_device_is_skipped(self) -> None:
        """A nonsense hour never becomes a fire time, even if newest."""
        published = [
            ("bad", _log(99, 0, hlc="2026-08-09T10:00:00.000Z-0000-bad")),
            ("good", _log(7, 20, hlc="2026-07-01T10:00:00.000Z-0000-good")),
        ]

        assert newest_alarm(published) == (7, 20)


class TestParseLog:
    def test_a_non_object_payload_yields_none(self) -> None:
        """A JSON array is valid JSON but not a log."""
        assert parse_log("[]") is None
