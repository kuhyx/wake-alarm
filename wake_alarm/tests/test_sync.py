"""Tests for _sync.py — reading the alarm the phone pushed, with fallbacks."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch
import urllib.error

import pytest

from wake_alarm._alarm_payload import extract_field, parse_log
from wake_alarm._sync import (
    Alarm,
    _fetch_github_alarm,
    _parse_args,
    _read_cache,
    _read_token,
    _read_token_fallback,
    _write_cache,
    get_alarm,
    main,
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


class TestAlarm:
    """Tests for the Alarm value object."""

    def test_str_pads_and_names_source(self) -> None:
        """Render zero-padded HH:MM with the source in parentheses."""
        assert str(Alarm(7, 5, "remote")) == "07:05 (remote)"


class TestReadToken:
    """Tests for _read_token."""

    def test_missing_file(self) -> None:
        """A missing config file yields no token."""
        assert _read_token() is None

    def test_malformed_json(self, config_file: Path) -> None:
        """Unparsable JSON yields no token."""
        config_file.write_text("{not json")
        assert _read_token() is None

    def test_not_a_dict(self, config_file: Path) -> None:
        """A JSON array is not a config object."""
        config_file.write_text("[]")
        assert _read_token() is None

    @pytest.mark.parametrize("value", [None, "", 42])
    def test_unusable_token_values(self, config_file: Path, value: object) -> None:
        """Absent, empty and non-string tokens are all rejected."""
        config_file.write_text(json.dumps({"token": value}))
        assert _read_token() is None

    def test_valid_token(self, config_file: Path) -> None:
        """A non-empty string token is returned."""
        config_file.write_text(json.dumps({"token": "ghp_x"}))
        assert _read_token() == "ghp_x"


class TestTokenFallback:
    """Tests for reusing a sibling companion app's token file."""

    def test_no_fallback_files(self) -> None:
        """With nothing on disk anywhere there is no token."""
        assert _read_token_fallback() is None
        assert _read_token() is None

    def test_reads_raw_single_line_token(
        self, fallback_files: tuple[Path, Path]
    ) -> None:
        """A sibling token file is a raw PAT, not JSON — and is stripped."""
        fallback_files[0].write_text("  ghp_sibling\n")
        assert _read_token_fallback() == "ghp_sibling"

    def test_skips_empty_file(self, fallback_files: tuple[Path, Path]) -> None:
        """An empty first file falls through to the second."""
        fallback_files[0].write_text("   \n")
        fallback_files[1].write_text("ghp_second")
        assert _read_token_fallback() == "ghp_second"

    def test_skips_unreadable_file(self, fallback_files: tuple[Path, Path]) -> None:
        """An unreadable file is skipped rather than fatal."""
        fallback_files[1].write_text("ghp_second")
        with patch(
            "pathlib.Path.read_text",
            side_effect=[OSError("denied"), "ghp_second"],
        ):
            assert _read_token_fallback() == "ghp_second"

    def test_own_config_wins(
        self, config_file: Path, fallback_files: tuple[Path, Path]
    ) -> None:
        """wake_alarm's own config takes precedence over a sibling's."""
        config_file.write_text(json.dumps({"token": "ghp_own"}))
        fallback_files[0].write_text("ghp_sibling")
        assert _read_token() == "ghp_own"

    def test_falls_back_when_config_absent(
        self, fallback_files: tuple[Path, Path]
    ) -> None:
        """With no own config, the sibling token is used."""
        fallback_files[0].write_text("ghp_sibling")
        assert _read_token() == "ghp_sibling"


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


class TestFetchRemoteAlarm:
    """Tests for the GitHub backend behind fetch_remote_alarm."""

    def test_no_token(self) -> None:
        """Without a token there is nothing to fetch."""
        assert _fetch_github_alarm() is None

    def _with_token(self, config_file: Path) -> None:
        config_file.write_text(json.dumps({"token": "ghp_x"}))

    def test_success(self, config_file: Path) -> None:
        """A 200 with a valid body yields the pair."""
        self._with_token(config_file)
        response = MagicMock()
        response.read.return_value = _log(6, 15).encode()
        response.__enter__.return_value = response
        with patch("urllib.request.urlopen", return_value=response):
            assert _fetch_github_alarm() == (6, 15)

    def test_sends_raw_media_type_and_auth(self, config_file: Path) -> None:
        """The request carries the token and the raw Accept header."""
        self._with_token(config_file)
        response = MagicMock()
        response.read.return_value = _log().encode()
        response.__enter__.return_value = response
        with patch("urllib.request.urlopen", return_value=response) as urlopen:
            _fetch_github_alarm()
        request = urlopen.call_args[0][0]
        assert request.get_header("Authorization") == "token ghp_x"
        assert request.get_header("Accept") == "application/vnd.github.raw"
        assert "kuhyx/syncs" in request.full_url

    def test_refuses_a_non_https_scheme(self, config_file: Path) -> None:
        """The token is never sent over a plaintext or file:// URL."""
        self._with_token(config_file)
        with (
            patch("wake_alarm._sync.SYNC_API_BASE", "http://api.github.com"),
            patch("urllib.request.urlopen") as urlopen,
        ):
            assert _fetch_github_alarm() is None
        urlopen.assert_not_called()

    @pytest.mark.parametrize(
        "exc",
        [
            urllib.error.URLError("down"),
            OSError("timeout"),
            UnicodeDecodeError("utf-8", b"\xff", 0, 1, "bad"),
        ],
    )
    def test_network_failures_yield_none(
        self, config_file: Path, exc: Exception
    ) -> None:
        """Every transport failure degrades to None, never raises."""
        self._with_token(config_file)
        with patch("urllib.request.urlopen", side_effect=exc):
            assert _fetch_github_alarm() is None


class TestCache:
    """Tests for the on-disk cache helpers."""

    def test_roundtrip(self, cache_file: Path) -> None:
        """A written cache reads back with the same values."""
        _write_cache(6, 45)
        cached = _read_cache()
        assert cached is not None
        assert cached[0] == 6
        assert cached[1] == 45

    def test_write_creates_parent_dir(self, cache_file: Path) -> None:
        """The cache directory is created on demand."""
        _write_cache(6, 45)
        assert cache_file.exists()

    def test_write_failure_is_swallowed(self) -> None:
        """An unwritable cache logs but does not raise."""
        with patch("pathlib.Path.mkdir", side_effect=OSError("read-only")):
            _write_cache(6, 45)

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
        _write_cache(6, 45)
        with patch("wake_alarm._sync.fetch_remote_alarm") as fetch:
            alarm = get_alarm()
        fetch.assert_not_called()
        assert (alarm.hour, alarm.minute, alarm.source) == (6, 45, "cache")

    def test_stale_cache_triggers_fetch(self, cache_file: Path) -> None:
        """An old cache entry is refreshed from the network."""
        _write_cache(6, 45)
        with patch("wake_alarm._sync.fetch_remote_alarm", return_value=(7, 0)):
            alarm = get_alarm(max_cache_age_seconds=0)
        assert (alarm.hour, alarm.minute, alarm.source) == (7, 0, "remote")

    def test_fetch_result_is_cached(self, cache_file: Path) -> None:
        """A successful fetch is written to the cache for next time."""
        with patch("wake_alarm._sync.fetch_remote_alarm", return_value=(7, 0)):
            get_alarm()
        assert json.loads(cache_file.read_text())["hour"] == 7

    def test_falls_back_to_stale_cache(self, cache_file: Path) -> None:
        """When the fetch fails, an old cache entry is still used."""
        _write_cache(6, 45)
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
        assert alarm.hour == 13


class TestCli:
    """Tests for the --show entry point."""

    def test_parse_args_defaults(self) -> None:
        """Both flags default to off."""
        args = _parse_args([])
        assert not args.show
        assert not args.no_cache

    def test_main_prints_alarm(self, capsys: pytest.CaptureFixture[str]) -> None:
        """main prints the resolved alarm."""
        with (
            patch("sys.argv", ["_sync", "--show"]),
            patch(
                "wake_alarm._sync.get_alarm",
                return_value=Alarm(7, 30, "remote"),
            ),
        ):
            main()
        assert "07:30 (remote)" in capsys.readouterr().out

    def test_no_cache_forces_live_read(self) -> None:
        """--no-cache asks get_alarm for a zero-age cache."""
        with (
            patch("sys.argv", ["_sync", "--no-cache"]),
            patch(
                "wake_alarm._sync.get_alarm",
                return_value=Alarm(7, 30, "remote"),
            ) as get,
        ):
            main()
        assert get.call_args.kwargs["max_cache_age_seconds"] == 0.0
