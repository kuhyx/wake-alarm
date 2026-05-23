"""Tests for _smart_plug.py — Tapo P110 control with config + asyncio."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from python_pkg.wake_alarm import _smart_plug
from python_pkg.wake_alarm._smart_plug import (
    _connect,
    _load_config,
    _run,
    _set_state,
    turn_off_plug,
    turn_on_plug,
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


class TestSetState:
    """Tests for _set_state()."""

    def test_noop_when_config_missing(self) -> None:
        """No config => no kasa calls."""
        with (
            patch.object(_smart_plug, "_load_config", return_value=None),
            patch.object(_smart_plug, "_connect") as mock_connect,
        ):
            asyncio.run(_set_state(on=True))
        mock_connect.assert_not_called()

    def test_noop_when_connect_returns_none(self) -> None:
        """Connect failure => no toggle."""
        with (
            patch.object(
                _smart_plug,
                "_load_config",
                return_value={"host": "h", "email": "e", "password": "p"},
            ),
            patch.object(_smart_plug, "_connect", new=AsyncMock(return_value=None)),
        ):
            asyncio.run(_set_state(on=True))

    def test_turns_on_when_on_true(self) -> None:
        """on=True calls dev.turn_on(), not turn_off()."""
        dev = MagicMock()
        dev.turn_on = AsyncMock()
        dev.turn_off = AsyncMock()
        dev.disconnect = AsyncMock()
        with (
            patch.object(
                _smart_plug,
                "_load_config",
                return_value={"host": "h", "email": "e", "password": "p"},
            ),
            patch.object(_smart_plug, "_connect", new=AsyncMock(return_value=dev)),
        ):
            asyncio.run(_set_state(on=True))
        dev.turn_on.assert_awaited_once()
        dev.turn_off.assert_not_called()
        dev.disconnect.assert_awaited_once()

    def test_turns_off_when_on_false(self) -> None:
        """on=False calls dev.turn_off(), not turn_on()."""
        dev = MagicMock()
        dev.turn_on = AsyncMock()
        dev.turn_off = AsyncMock()
        dev.disconnect = AsyncMock()
        with (
            patch.object(
                _smart_plug,
                "_load_config",
                return_value={"host": "h", "email": "e", "password": "p"},
            ),
            patch.object(_smart_plug, "_connect", new=AsyncMock(return_value=dev)),
        ):
            asyncio.run(_set_state(on=False))
        dev.turn_off.assert_awaited_once()
        dev.turn_on.assert_not_called()

    def test_swallows_toggle_oserror_and_still_disconnects(self) -> None:
        """A toggle OSError is swallowed; disconnect still runs."""
        dev = MagicMock()
        dev.turn_on = AsyncMock(side_effect=OSError)
        dev.disconnect = AsyncMock()
        with (
            patch.object(
                _smart_plug,
                "_load_config",
                return_value={"host": "h", "email": "e", "password": "p"},
            ),
            patch.object(_smart_plug, "_connect", new=AsyncMock(return_value=dev)),
        ):
            asyncio.run(_set_state(on=True))
        dev.disconnect.assert_awaited_once()

    def test_swallows_disconnect_oserror(self) -> None:
        """A disconnect OSError after a successful toggle is suppressed."""
        dev = MagicMock()
        dev.turn_on = AsyncMock()
        dev.disconnect = AsyncMock(side_effect=OSError)
        with (
            patch.object(
                _smart_plug,
                "_load_config",
                return_value={"host": "h", "email": "e", "password": "p"},
            ),
            patch.object(_smart_plug, "_connect", new=AsyncMock(return_value=dev)),
        ):
            asyncio.run(_set_state(on=True))


# ---------------------------------------------------------------------------
# _run, turn_on_plug, turn_off_plug
# ---------------------------------------------------------------------------


class TestRun:
    """Tests for _run() and the sync wrappers."""

    def test_noop_when_kasa_unavailable(self) -> None:
        """When kasa import failed, _run returns silently."""
        with (
            patch.object(_smart_plug, "_KASA_AVAILABLE", new=False),
            patch.object(_smart_plug, "_set_state") as mock_set_state,
        ):
            _run(on=True)
        mock_set_state.assert_not_called()

    @pytest.mark.usefixtures("_kasa_available")
    def test_invokes_set_state(self) -> None:
        """When kasa is available, _set_state runs via asyncio.run."""
        with patch.object(_smart_plug, "_set_state", new=AsyncMock()) as mock_set_state:
            _run(on=True)
        mock_set_state.assert_awaited_once_with(on=True)

    @pytest.mark.usefixtures("_kasa_available")
    def test_swallows_timeout(self) -> None:
        """A timeout from asyncio.wait_for is suppressed."""

        async def _hang(**_: bool) -> None:
            await asyncio.sleep(10)

        with (
            patch.object(_smart_plug, "_set_state", new=_hang),
            patch.object(_smart_plug, "TAPO_TIMEOUT_SECONDS", 0.01),
        ):
            _run(on=True)

    @pytest.mark.usefixtures("_kasa_available")
    def test_swallows_oserror(self) -> None:
        """An OSError raised from _set_state is suppressed."""
        with patch.object(
            _smart_plug, "_set_state", new=AsyncMock(side_effect=OSError)
        ):
            _run(on=True)

    @pytest.mark.usefixtures("_kasa_available")
    def test_swallows_runtimeerror(self) -> None:
        """A RuntimeError raised from _set_state is suppressed."""
        with patch.object(
            _smart_plug, "_set_state", new=AsyncMock(side_effect=RuntimeError)
        ):
            _run(on=True)

    @pytest.mark.usefixtures("_kasa_available")
    def test_turn_on_plug_delegates(self) -> None:
        """turn_on_plug calls _run with on=True."""
        with patch.object(_smart_plug, "_run") as mock_run:
            turn_on_plug()
        mock_run.assert_called_once_with(on=True)

    @pytest.mark.usefixtures("_kasa_available")
    def test_turn_off_plug_delegates(self) -> None:
        """turn_off_plug calls _run with on=False."""
        with patch.object(_smart_plug, "_run") as mock_run:
            turn_off_plug()
        mock_run.assert_called_once_with(on=False)


class TestKasaImportFallback:
    """Cover the ImportError branch of the optional ``kasa`` import."""

    def test_module_sets_kasa_unavailable_when_import_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Reloading the module with ``kasa`` blocked sets _KASA_AVAILABLE=False."""
        import importlib
        import sys

        monkeypatch.setitem(sys.modules, "kasa", None)
        monkeypatch.setitem(sys.modules, "kasa.exceptions", None)
        try:
            reloaded = importlib.reload(_smart_plug)
            assert reloaded._KASA_AVAILABLE is False
        finally:
            monkeypatch.undo()
            importlib.reload(_smart_plug)
