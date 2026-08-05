"""Tests for the Firebase/GitHub backend selection in _sync.py.

Split out of ``test_sync.py`` to keep both files under the repo's 500-line
cap; the parse, cache and CLI tests stay there.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from wake_alarm._constants import SYNC_ALARM_PATH
from wake_alarm._sync import _fetch_firebase_alarm, fetch_remote_alarm

if TYPE_CHECKING:
    from contextlib import AbstractContextManager


class _FakeConfigError(Exception):
    """Stand-in for crdt_sync.ConfigError, which is optional at runtime."""


class _FakeAuthError(Exception):
    """Stand-in for crdt_sync's FirebaseAuthError."""


class _FakeRemoteError(Exception):
    """Stand-in for crdt_sync's RemoteSyncError."""


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


class TestFetchFirebaseAlarm:
    """Tests for the Firebase backend behind fetch_remote_alarm."""

    def _patched(
        self, *, client: MagicMock | None = None, configured: bool = True
    ) -> AbstractContextManager[None]:
        """Patch the module-level crdt_sync bindings for one test.

        crdt_sync is an optional dependency imported at module scope, so the
        tests drive its bound names directly rather than requiring it to be
        installed -- the same contract production degrades against.
        """
        config = MagicMock()
        config.is_file.return_value = configured
        return patch.multiple(
            "wake_alarm._sync",
            _FIREBASE_AVAILABLE=True,
            FIREBASE_CONFIG_FILE=config,
            firebase_client_for=MagicMock(
                return_value=client if client is not None else MagicMock()
            ),
            ConfigError=_FakeConfigError,
            FirebaseAuthError=_FakeAuthError,
            RemoteSyncError=_FakeRemoteError,
        )

    def test_missing_dependency_yields_none(self) -> None:
        """A machine without crdt_sync falls back instead of raising."""
        with patch("wake_alarm._sync._FIREBASE_AVAILABLE", new=False):
            assert _fetch_firebase_alarm() is None

    def test_unconfigured_never_touches_the_network(self) -> None:
        """With no config file, no client is ever constructed."""
        client = MagicMock()
        with self._patched(client=client, configured=False):
            assert _fetch_firebase_alarm() is None
        client.get_file_text.assert_not_called()

    def test_success(self) -> None:
        """A published alarm parses to its (hour, minute) pair."""
        client = MagicMock()
        client.get_file_text.return_value = _log(6, 15)
        with self._patched(client=client):
            assert _fetch_firebase_alarm() == (6, 15)
        client.get_file_text.assert_called_once_with(SYNC_ALARM_PATH)

    def test_absent_value_yields_none(self) -> None:
        """Nothing published yet is a miss, not a crash."""
        client = MagicMock()
        client.get_file_text.return_value = None
        with self._patched(client=client):
            assert _fetch_firebase_alarm() is None

    @pytest.mark.parametrize(
        "exc",
        [
            _FakeConfigError("bad config"),
            _FakeAuthError("rejected"),
            _FakeRemoteError("database down"),
            OSError("no route to host"),
        ],
    )
    def test_failures_yield_none(self, exc: Exception) -> None:
        """Every Firebase failure degrades to None, never raises."""
        client = MagicMock()
        client.get_file_text.side_effect = exc
        with self._patched(client=client):
            assert _fetch_firebase_alarm() is None


class TestOptionalCrdtSyncImport:
    """Cover the ImportError branch of the optional ``crdt_sync`` import."""

    def test_module_sets_firebase_unavailable_when_import_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Reloading with crdt_sync blocked sets _FIREBASE_AVAILABLE=False."""
        import importlib
        import sys

        from wake_alarm import _sync

        for name in (
            "crdt_sync",
            "crdt_sync._config",
            "crdt_sync._firebase_auth",
            "crdt_sync._remote",
        ):
            monkeypatch.setitem(sys.modules, name, None)
        try:
            reloaded = importlib.reload(_sync)
            assert reloaded._FIREBASE_AVAILABLE is False
        finally:
            monkeypatch.undo()
            importlib.reload(_sync)


class TestFetchRemoteAlarmDispatch:
    """Tests for the Firebase-first, GitHub-fallback ordering."""

    def test_prefers_firebase(self) -> None:
        """When Firebase answers, GitHub is never asked."""
        with (
            patch("wake_alarm._sync._fetch_firebase_alarm", return_value=(6, 15)),
            patch("wake_alarm._sync._fetch_github_alarm") as github,
        ):
            assert fetch_remote_alarm() == (6, 15)
        github.assert_not_called()

    def test_falls_back_to_github(self) -> None:
        """A Firebase miss still resolves through the mirror."""
        with (
            patch("wake_alarm._sync._fetch_firebase_alarm", return_value=None),
            patch("wake_alarm._sync._fetch_github_alarm", return_value=(7, 30)),
        ):
            assert fetch_remote_alarm() == (7, 30)

    def test_both_missing_yields_none(self) -> None:
        """With neither backend usable the caller degrades to the cache."""
        with (
            patch("wake_alarm._sync._fetch_firebase_alarm", return_value=None),
            patch("wake_alarm._sync._fetch_github_alarm", return_value=None),
        ):
            assert fetch_remote_alarm() is None
