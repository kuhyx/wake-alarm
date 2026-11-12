"""Tests for _sync.py — reading the alarm the phone pushed, with fallbacks."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from crdt_sync import RemoteSyncError, open_encrypted_client
import pytest

from wake_alarm._constants import (
    FALLBACK_ALARM_HOUR,
    SYNC_LEGACY_PREFIX,
)
from wake_alarm._sync import (
    Alarm,
    _fetch_github_alarm,
    _read_cache,
    _write_cache,
    get_alarm,
)
from wake_alarm.tests.conftest import TEST_ARGON2, TEST_PHRASE, DictStore

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


class TestAlarm:
    """Tests for the Alarm value object."""

    def test_str_pads_and_names_source(self) -> None:
        """Render zero-padded HH:MM with the source in parentheses."""
        assert str(Alarm(7, 5, "remote")) == "07:05 (remote)"


def _records(text: str) -> object:
    """Serve ``text`` for every record path, beside a phone-made header."""
    header = {}

    def _get(path: str) -> str | None:
        if path.endswith("/e2e"):
            if not header:
                header["h"] = _phone_header()
            return header["h"]
        return text

    return _get


def _phone_header() -> str:
    store = DictStore()
    open_encrypted_client(
        store, SYNC_LEGACY_PREFIX, passphrase=TEST_PHRASE, params=TEST_ARGON2
    )
    return store.files["wake-alarm-sync/e2e"]


class TestFetchRemoteAlarm:
    """Tests for the GitHub backend behind fetch_remote_alarm."""

    def test_no_token(self) -> None:
        """Without a token there is nothing to fetch."""
        assert _fetch_github_alarm() is None

    def _with_token(self, config_file: Path) -> None:
        config_file.write_text(json.dumps({"token": "ghp_x"}))

    def _client(self, **methods: object) -> MagicMock:
        """A Contents API client stand-in; never the network."""
        client = MagicMock()
        for name, value in methods.items():
            setattr(client, name, value)
        return client

    def test_success(self, config_file: Path) -> None:
        """A published log through the (encrypting) client yields the pair."""
        self._with_token(config_file)
        client = self._client(
            list_directory=MagicMock(return_value=["phone"]),
            get_file_text=MagicMock(side_effect=_records(_log(6, 15))),
        )
        del client.get_string_map
        with patch("wake_alarm._sync_transport.GitHubSyncClient", return_value=client):
            fetched = _fetch_github_alarm()
            assert fetched is not None
            assert fetched[:2] == (6, 15)

    def test_unparseable_body_is_not_an_alarm(self, config_file: Path) -> None:
        """A body that is not a usable log yields nothing, not a crash."""
        self._with_token(config_file)
        client = self._client(
            list_directory=MagicMock(return_value=["phone"]),
            get_file_text=MagicMock(side_effect=_records("{}")),
        )
        del client.get_string_map
        with patch("wake_alarm._sync_transport.GitHubSyncClient", return_value=client):
            assert _fetch_github_alarm() is None

    @pytest.mark.parametrize("exc", [RemoteSyncError("down"), OSError("timeout")])
    def test_network_failures_yield_none(
        self, config_file: Path, exc: Exception
    ) -> None:
        """Every transport failure degrades to None, never raises."""
        self._with_token(config_file)
        client = self._client(get_file_text=MagicMock(side_effect=exc))
        with patch("wake_alarm._sync_transport.GitHubSyncClient", return_value=client):
            assert _fetch_github_alarm() is None


class TestCache:
    """Tests for the on-disk cache helpers."""

    def test_roundtrip(self, cache_file: Path) -> None:
        """A written cache reads back with the same values."""
        _write_cache(6, 45, None)
        cached = _read_cache()
        assert cached is not None
        assert cached[0] == 6
        assert cached[1] == 45

    def test_write_creates_parent_dir(self, cache_file: Path) -> None:
        """The cache directory is created on demand."""
        _write_cache(6, 45, None)
        assert cache_file.exists()

    def test_write_failure_is_swallowed(self) -> None:
        """An unwritable cache logs but does not raise."""
        with patch("pathlib.Path.mkdir", side_effect=OSError("read-only")):
            _write_cache(6, 45, None)

    def test_missing_file(self) -> None:
        """No cache file yields None."""
        assert _read_cache() is None

    @pytest.mark.parametrize(
        "content",
        [
            "{not json",
            "[]",
            json.dumps({"hour": "6", "minute": 45, "fetched_at": 1.0}),
            json.dumps({"hour": 6, "minute": "45", "fetched_at": 1.0}),
            json.dumps({"hour": 6, "minute": 45, "fetched_at": "soon"}),
            json.dumps({"hour": 24, "minute": 45, "fetched_at": 1.0}),
            json.dumps({"hour": 6, "minute": 60, "fetched_at": 1.0}),
        ],
    )
    def test_malformed_cache_yields_none(self, cache_file: Path, content: str) -> None:
        """Any unexpected cache shape is treated as no cache."""
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(content)
        assert _read_cache() is None


class TestGetAlarm:
    """Tests for the get_alarm resolution chain."""

    def test_fresh_cache_skips_network(self, cache_file: Path) -> None:
        """A young cache entry is served without any fetch."""
        _write_cache(6, 45, None)
        with patch("wake_alarm._sync.fetch_remote_alarm") as fetch:
            alarm = get_alarm()
        fetch.assert_not_called()
        assert (alarm.hour, alarm.minute, alarm.source) == (6, 45, "cache")

    def test_stale_cache_triggers_fetch(self, cache_file: Path) -> None:
        """An old cache entry is refreshed from the network."""
        _write_cache(6, 45, None)
        with patch("wake_alarm._sync.fetch_remote_alarm", return_value=(7, 0, None)):
            alarm = get_alarm(max_cache_age_seconds=0)
        assert (alarm.hour, alarm.minute, alarm.source) == (7, 0, "remote")

    def test_fetch_result_is_cached(self, cache_file: Path) -> None:
        """A successful fetch is written to the cache for next time."""
        with patch("wake_alarm._sync.fetch_remote_alarm", return_value=(7, 0, None)):
            get_alarm()
        assert json.loads(cache_file.read_text())["hour"] == 7

    def test_falls_back_to_stale_cache(self, cache_file: Path) -> None:
        """When the fetch fails, an old cache entry is still used."""
        _write_cache(6, 45, None)
        with patch("wake_alarm._sync.fetch_remote_alarm", return_value=None):
            alarm = get_alarm(max_cache_age_seconds=0)
        assert (alarm.hour, alarm.minute, alarm.source) == (
            6,
            45,
            "stale-cache",
        )

    def test_falls_back_to_constant(self) -> None:
        """With no cache and no network, the fixed fallback hour is used."""
        with patch("wake_alarm._sync.fetch_remote_alarm", return_value=None):
            alarm = get_alarm()
        assert (alarm.minute, alarm.source) == (0, "fallback")
        # Bound to the constant, not a literal: the fallback deliberately
        # matches the phone's baked-in baseline, so hardcoding the number here
        # would fail every time that shared value moves.
        assert alarm.hour == FALLBACK_ALARM_HOUR
