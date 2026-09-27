"""Tests for _sync.py — reading the alarm the phone pushed, with fallbacks."""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from wake_alarm._constants import (
    FALLBACK_ALARM_HOUR,
    PUBLISHED_ALARM_MAX_AGE_SECONDS,
)
from wake_alarm._sync import (
    get_alarm,
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
        patch("wake_alarm._sync_transport.SYNC_CONFIG_FILE", config_file),
        patch("wake_alarm._sync.ALARM_CACHE_FILE", cache_file),
        patch("wake_alarm._sync_transport.SYNC_TOKEN_FALLBACK_FILES", fallback_files),
    ):
        yield


class TestLapsedPublishedAlarm:
    """The phone must keep saying it, not just have said it once.

    A publishing bug on the phone left one record stamped 2026-08-09 and the
    PC honoured it for three weeks: a publish that never happens looks exactly
    like one that has not changed, so the last successful publish is
    authoritative forever. These pin the guard that ends that.
    """

    def test_a_lapsed_remote_is_not_used(self, tmp_path: Path) -> None:
        """A record older than the max age falls through to the fallback."""
        ancient = time.time() - PUBLISHED_ALARM_MAX_AGE_SECONDS - 1
        with (
            patch("wake_alarm._sync.ALARM_CACHE_FILE", tmp_path / "cache.json"),
            patch(
                "wake_alarm._sync.fetch_remote_alarm",
                return_value=(7, 0, ancient),
            ),
        ):
            alarm = get_alarm()
        assert alarm.source == "fallback"
        assert alarm.hour == FALLBACK_ALARM_HOUR

    def test_a_recent_remote_is_used(self, tmp_path: Path) -> None:
        """A freshly stamped record is honoured as normal."""
        with (
            patch("wake_alarm._sync.ALARM_CACHE_FILE", tmp_path / "cache.json"),
            patch(
                "wake_alarm._sync.fetch_remote_alarm",
                return_value=(7, 0, time.time()),
            ),
        ):
            alarm = get_alarm()
        assert (alarm.hour, alarm.minute, alarm.source) == (7, 0, "remote")

    def test_an_undated_remote_is_trusted(self, tmp_path: Path) -> None:
        """No stamp means "cannot tell", which must not mean "expired".

        The GitHub mirror reads a single fixed path with no per-field HLC, so
        rejecting undated records would break that whole backend.
        """
        with (
            patch("wake_alarm._sync.ALARM_CACHE_FILE", tmp_path / "cache.json"),
            patch(
                "wake_alarm._sync.fetch_remote_alarm",
                return_value=(7, 0, None),
            ),
        ):
            alarm = get_alarm()
        assert alarm.source == "remote"

    def test_a_lapsed_cache_is_not_served(self, tmp_path: Path) -> None:
        """The check is on when the PHONE said it, not when we fetched.

        Without this the guard is trivially defeated: the cache is rewritten
        from the same stale record every few minutes, so `fetched_at` is
        always fresh no matter how old the record behind it is.
        """
        cache = tmp_path / "cache.json"
        cache.write_text(
            json.dumps(
                {
                    "hour": 7,
                    "minute": 0,
                    "fetched_at": time.time(),
                    "published_at": time.time() - PUBLISHED_ALARM_MAX_AGE_SECONDS - 1,
                }
            )
        )
        with (
            patch("wake_alarm._sync.ALARM_CACHE_FILE", cache),
            patch("wake_alarm._sync.fetch_remote_alarm", return_value=None),
        ):
            alarm = get_alarm()
        assert alarm.source == "fallback"

    def test_the_publish_instant_round_trips_through_the_cache(
        self, tmp_path: Path
    ) -> None:
        """A fetched record's age survives being cached."""
        cache = tmp_path / "cache.json"
        stamped = time.time() - 60
        with (
            patch("wake_alarm._sync.ALARM_CACHE_FILE", cache),
            patch(
                "wake_alarm._sync.fetch_remote_alarm",
                return_value=(7, 0, stamped),
            ),
        ):
            get_alarm()
        assert json.loads(cache.read_text())["published_at"] == stamped
