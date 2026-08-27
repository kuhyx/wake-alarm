"""Tests for _sync.py's GitHub token discovery and its sibling fallbacks.

Split out of test_sync.py to hold both files under the 250-line gate.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from wake_alarm._sync import (
    _read_token,
    _read_token_fallback,
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
