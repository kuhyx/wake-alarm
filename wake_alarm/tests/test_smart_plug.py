"""Tests for _smart_plug.py — Tapo P110 control with config + asyncio."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from wake_alarm import _smart_plug
from wake_alarm._smart_plug import (
    _connect,
    _load_config,
)

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config_file(tmp_path: Path, contents: object) -> Path:
    """Write ``contents`` (encoded as JSON unless str) to a config file."""
    path = tmp_path / "tapo.json"
    if isinstance(contents, str):
        path.write_text(contents, encoding="utf-8")
    else:
        path.write_text(json.dumps(contents), encoding="utf-8")
    return path


@pytest.fixture
def _kasa_available() -> Generator[None]:
    """Force _smart_plug to treat ``kasa`` as importable for the test."""
    with patch.object(_smart_plug, "_KASA_AVAILABLE", new=True):
        yield


# ---------------------------------------------------------------------------
# _load_config
# ---------------------------------------------------------------------------


class TestLoadConfig:
    """Tests for _load_config()."""

    def test_returns_none_when_file_missing(self, tmp_path: Path) -> None:
        """Missing config file returns None."""
        with patch.object(_smart_plug, "TAPO_CONFIG_FILE", tmp_path / "missing.json"):
            assert _load_config() is None

    def test_returns_none_for_invalid_json(self, tmp_path: Path) -> None:
        """Malformed JSON returns None."""
        path = _make_config_file(tmp_path, "{not valid json")
        with patch.object(_smart_plug, "TAPO_CONFIG_FILE", path):
            assert _load_config() is None

    def test_returns_none_when_top_level_not_dict(self, tmp_path: Path) -> None:
        """A JSON list at top level returns None."""
        path = _make_config_file(tmp_path, ["host", "email", "password"])
        with patch.object(_smart_plug, "TAPO_CONFIG_FILE", path):
            assert _load_config() is None

    def test_returns_none_when_key_missing(self, tmp_path: Path) -> None:
        """Missing required key returns None."""
        path = _make_config_file(tmp_path, {"host": "1.2.3.4", "email": "x"})
        with patch.object(_smart_plug, "TAPO_CONFIG_FILE", path):
            assert _load_config() is None

    def test_returns_none_when_value_empty(self, tmp_path: Path) -> None:
        """Empty-string value returns None."""
        path = _make_config_file(
            tmp_path, {"host": "1.2.3.4", "email": "", "password": "p"}
        )
        with patch.object(_smart_plug, "TAPO_CONFIG_FILE", path):
            assert _load_config() is None

    def test_returns_none_when_value_not_string(self, tmp_path: Path) -> None:
        """Non-string value returns None."""
        path = _make_config_file(
            tmp_path, {"host": 1234, "email": "e", "password": "p"}
        )
        with patch.object(_smart_plug, "TAPO_CONFIG_FILE", path):
            assert _load_config() is None

    def test_returns_validated_dict(self, tmp_path: Path) -> None:
        """Valid config returns a normalized dict with only required keys."""
        path = _make_config_file(
            tmp_path,
            {
                "host": "192.168.1.50",
                "email": "user@example.com",
                "password": "secret",
                "extra": "ignored",
            },
        )
        with patch.object(_smart_plug, "TAPO_CONFIG_FILE", path):
            assert _load_config() == {
                "host": "192.168.1.50",
                "email": "user@example.com",
                "password": "secret",
            }


# ---------------------------------------------------------------------------
# _connect
# ---------------------------------------------------------------------------


class TestConnect:
    """Tests for _connect()."""

    def test_returns_device_on_success(self) -> None:
        """Successful discover + update returns the device."""
        dev = MagicMock()
        dev.update = AsyncMock()
        dev.disconnect = AsyncMock()
        with (
            patch.object(_smart_plug, "Discover") as mock_discover,
            patch.object(_smart_plug, "Credentials") as mock_creds,
        ):
            mock_discover.discover_single = AsyncMock(return_value=dev)
            result = asyncio.run(
                _connect({"host": "1.2.3.4", "email": "e", "password": "p"})
            )
        assert result is dev
        mock_creds.assert_called_once_with("e", "p")

    def test_returns_none_when_discover_raises_oserror(self) -> None:
        """OSError during discovery returns None."""
        with patch.object(_smart_plug, "Discover") as mock_discover:
            mock_discover.discover_single = AsyncMock(side_effect=OSError)
            result = asyncio.run(_connect({"host": "h", "email": "e", "password": "p"}))
        assert result is None

    def test_returns_none_when_update_raises(self) -> None:
        """Failure during update returns None and attempts disconnect."""
        dev = MagicMock()
        dev.update = AsyncMock(side_effect=OSError)
        dev.disconnect = AsyncMock()
        with patch.object(_smart_plug, "Discover") as mock_discover:
            mock_discover.discover_single = AsyncMock(return_value=dev)
            result = asyncio.run(_connect({"host": "h", "email": "e", "password": "p"}))
        assert result is None
        dev.disconnect.assert_awaited_once()

    def test_swallows_disconnect_failure_after_update_error(self) -> None:
        """A disconnect error after a failed update is suppressed."""
        dev = MagicMock()
        dev.update = AsyncMock(side_effect=OSError)
        dev.disconnect = AsyncMock(side_effect=OSError)
        with patch.object(_smart_plug, "Discover") as mock_discover:
            mock_discover.discover_single = AsyncMock(return_value=dev)
            result = asyncio.run(_connect({"host": "h", "email": "e", "password": "p"}))
        assert result is None


# ---------------------------------------------------------------------------
# _set_state
# ---------------------------------------------------------------------------
