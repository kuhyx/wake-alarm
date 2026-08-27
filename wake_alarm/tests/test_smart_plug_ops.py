"""Tests for _smart_plug.py's device operations — set_state, run, and the
kasa import fallback.

Split out of test_smart_plug.py for the 250-line gate; that file keeps
config loading and connection."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from wake_alarm import _smart_plug
from wake_alarm._smart_plug import (
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
