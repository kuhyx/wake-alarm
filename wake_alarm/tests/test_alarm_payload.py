"""Tests for _alarm_payload.py — parsing and ranking what the phone pushed.

Split out of test_sync.py: these exercise the wire format, which is a
different module from the fetching/caching this file's siblings cover.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest

from wake_alarm._alarm_payload import (
    extract_field,
    extract_hlc,
    newest_alarm,
    parse_log,
)

if TYPE_CHECKING:
    from pathlib import Path


def _log(hour: object = 7, minute: object = 30) -> str:
    """Build a crdt_sync log payload shaped like the phone's."""
    return json.dumps(
        {
            "alarm": {
                "fields": {
                    "alarm_hour": [hour, "hlc-1"],
                    "alarm_minute": [minute, "hlc-1"],
                }
            }
        }
    )


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    """Provide a temporary sync config path."""
    return tmp_path / "sync.json"


@pytest.fixture
def cache_file(tmp_path: Path) -> Path:
    """Provide a temporary alarm cache path."""
    return tmp_path / "cache" / "alarm_cache.json"


@pytest.fixture
def fallback_files(tmp_path: Path) -> tuple[Path, Path]:
    """Provide two temporary sibling-app token paths."""
    return tmp_path / "diet_guard_token", tmp_path / "screen_locker_token"


@pytest.fixture(autouse=True)
def _patch_paths(
    config_file: Path, cache_file: Path, fallback_files: tuple[Path, Path]
) -> None:
    """Redirect every on-disk path into tmp_path for every test."""
    with (
        patch("wake_alarm._sync.SYNC_CONFIG_FILE", config_file),
        patch("wake_alarm._sync.ALARM_CACHE_FILE", cache_file),
        patch("wake_alarm._sync.SYNC_TOKEN_FALLBACK_FILES", fallback_files),
    ):
        yield


class TestExtractField:
    """Tests for extract_field's tolerance of malformed logs."""

    @pytest.mark.parametrize(
        "log",
        [
            {},
            {"alarm": "not a dict"},
            {"alarm": {}},
            {"alarm": {"fields": "not a dict"}},
            {"alarm": {"fields": {}}},
            {"alarm": {"fields": {"alarm_hour": "not a list"}}},
            {"alarm": {"fields": {"alarm_hour": []}}},
            {"alarm": {"fields": {"alarm_hour": ["7", "hlc"]}}},
            {"alarm": {"fields": {"alarm_hour": [True, "hlc"]}}},
        ],
    )
    def test_malformed_shapes_yield_none(self, log: dict[str, Any]) -> None:
        """Every unexpected shape degrades to None rather than raising."""
        assert extract_field(log, "alarm_hour") is None

    def test_extracts_value(self) -> None:
        """The value is element 0 of the (value, HLC) pair."""
        log = {"alarm": {"fields": {"alarm_hour": [6, "hlc"]}}}
        assert extract_field(log, "alarm_hour") == 6


class TestParseLog:
    """Tests for parse_log."""

    def test_valid(self) -> None:
        """A well-formed log parses to an (hour, minute) pair."""
        assert parse_log(_log(7, 30)) == (7, 30)

    def test_invalid_json(self) -> None:
        """Unparsable JSON yields None."""
        assert parse_log("{nope") is None

    def test_not_a_dict(self) -> None:
        """A JSON array is not a log."""
        assert parse_log("[]") is None

    def test_missing_fields(self) -> None:
        """A log without the alarm fields yields None."""
        assert parse_log(json.dumps({"alarm": {"fields": {}}})) is None

    @pytest.mark.parametrize(("hour", "minute"), [(24, 0), (-1, 0), (7, 60), (7, -1)])
    def test_out_of_range(self, hour: int, minute: int) -> None:
        """Values outside 0-23 / 0-59 are rejected."""
        assert parse_log(_log(hour, minute)) is None


class TestExtractHlc:
    """The HLC stamp is how the newest device's alarm wins the ranking."""

    def test_returns_the_stamp_from_a_well_formed_pair(self) -> None:
        """A `[value, hlc]` pair yields its second element."""
        log = {"alarm": {"fields": {"alarm_hour": [7, "2026-08-27T06:00:00Z"]}}}
        assert extract_hlc(log, "alarm_hour") == "2026-08-27T06:00:00Z"

    def test_a_missing_field_ranks_below_every_real_stamp(self) -> None:
        """Empty string sorts first, so a malformed device never outranks."""
        assert extract_hlc({"alarm": {"fields": {}}}, "alarm_hour") == ""

    def test_a_short_pair_ranks_below_every_real_stamp(self) -> None:
        """A value with no stamp is unusable for ranking."""
        log = {"alarm": {"fields": {"alarm_hour": [7]}}}
        assert extract_hlc(log, "alarm_hour") == ""

    def test_a_non_string_stamp_is_rejected(self) -> None:
        """A numeric stamp would compare wrongly against real ISO strings."""
        log = {"alarm": {"fields": {"alarm_hour": [7, 12345]}}}
        assert extract_hlc(log, "alarm_hour") == ""


class TestNewestAlarm:
    """Ranking every device's published alarm, newest HLC wins."""

    def test_no_devices_at_all_yields_none(self) -> None:
        """An empty listing must not be mistaken for a valid alarm."""
        assert newest_alarm([]) is None

    def test_every_device_unusable_yields_none(self) -> None:
        """A device whose payload will not parse is skipped, not trusted."""
        assert newest_alarm([("phone", "not json"), ("tablet", "{}")]) is None

    def test_the_newest_hlc_wins(self) -> None:
        """The point of the stamp: the most recently set alarm is used."""
        older = json.dumps(
            {
                "alarm": {
                    "fields": {
                        "alarm_hour": [6, "2026-08-26T06:00:00Z"],
                        "alarm_minute": [0, "2026-08-26T06:00:00Z"],
                    }
                }
            },
        )
        newer = json.dumps(
            {
                "alarm": {
                    "fields": {
                        "alarm_hour": [7, "2026-08-27T06:00:00Z"],
                        "alarm_minute": [30, "2026-08-27T06:00:00Z"],
                    }
                }
            },
        )
        assert newest_alarm([("old", older), ("new", newer)]) == (7, 30)

    def test_an_unusable_device_does_not_block_a_good_one(self) -> None:
        """One broken device must not cost the user their alarm."""
        good = json.dumps(
            {
                "alarm": {
                    "fields": {
                        "alarm_hour": [5, "2026-08-27T06:00:00Z"],
                        "alarm_minute": [15, "2026-08-27T06:00:00Z"],
                    }
                }
            },
        )
        assert newest_alarm([("broken", "{}"), ("good", good)]) == (5, 15)
