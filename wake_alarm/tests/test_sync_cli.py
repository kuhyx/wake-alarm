"""Tests for `python -m wake_alarm._sync --show`, the documented CLI.

Split out of test_sync.py for the 250-line gate. Kept as its own file
because a CLI extracted to a new module has silently broken before:
it printed nothing and exited 0, invisible to every linter and the suite.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from wake_alarm._sync import (
    Alarm,
    _parse_args,
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
        patch("wake_alarm._sync_transport.SYNC_CONFIG_FILE", config_file),
        patch("wake_alarm._sync.ALARM_CACHE_FILE", cache_file),
        patch("wake_alarm._sync_transport.SYNC_TOKEN_FALLBACK_FILES", fallback_files),
    ):
        yield


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
