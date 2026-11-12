"""Tests for the Firebase/GitHub backend selection in _sync.py.

Split out of ``test_sync.py`` to keep both files under the repo's 500-line
cap; the parse, cache and CLI tests stay there.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from crdt_sync import E2eLayout
import pytest

from wake_alarm._constants import (
    SYNC_ALARM_FILENAME,
    SYNC_ALARM_PATH,
    SYNC_DEVICES_PREFIX,
)
from wake_alarm._sync import _fetch_firebase_alarm

if TYPE_CHECKING:
    from contextlib import AbstractContextManager


class _FakeConfigError(Exception):
    """Stand-in for crdt_sync.ConfigError, which is optional at runtime."""


class _FakeAuthError(Exception):
    """Stand-in for crdt_sync's FirebaseAuthError."""


class _FakeRemoteError(Exception):
    """Stand-in for crdt_sync's RemoteSyncError."""


def _log(hour: object = 7, minute: object = 30, hlc: str = "hlc-1") -> str:
    """Build a crdt_sync log payload shaped like the phone's."""
    return json.dumps(
        {
            "alarm": {
                "fields": {
                    "alarm_hour": [hour, hlc],
                    "alarm_minute": [minute, hlc],
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
            "wake_alarm._sync_transport",
            _FIREBASE_AVAILABLE=True,
            FIREBASE_CONFIG_FILE=config,
            firebase_client_for=MagicMock(
                return_value=client if client is not None else MagicMock()
            ),
            # Ranking and fallback are under test here, not encryption
            # (test_sync_e2e.py): a pass-through open on the E2E layout.
            open_encrypted_client=lambda store, old, **_: (store, E2eLayout.of(old)),
            ConfigError=_FakeConfigError,
            FirebaseAuthError=_FakeAuthError,
            RemoteSyncError=_FakeRemoteError,
        )

    def test_missing_dependency_yields_none(self) -> None:
        """A machine without crdt_sync falls back instead of raising."""
        with patch("wake_alarm._sync_transport._FIREBASE_AVAILABLE", new=False):
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
        client.list_directory.return_value = []
        client.get_file_text.return_value = _log(6, 15)
        with self._patched(client=client):
            fetched = _fetch_firebase_alarm()
            assert fetched is not None
            assert fetched[:2] == (6, 15)
        client.get_file_text.assert_called_once_with(SYNC_ALARM_PATH)

    def test_absent_value_yields_none(self) -> None:
        """Nothing published yet is a miss, not a crash."""
        client = MagicMock()
        client.list_directory.return_value = []
        client.get_file_text.return_value = None
        with self._patched(client=client):
            assert _fetch_firebase_alarm() is None

    def test_reads_a_discovered_device_directory(self) -> None:
        """A phone publishing under a uuid is found by listing, not by path."""
        client = MagicMock()
        client.list_directory.return_value = ["7f3c-uuid"]
        client.get_file_text.return_value = _log(6, 45)
        with self._patched(client=client):
            fetched = _fetch_firebase_alarm()
            assert fetched is not None
            assert fetched[:2] == (6, 45)
        client.get_file_text.assert_called_once_with(
            f"{SYNC_DEVICES_PREFIX}/7f3c-uuid/{SYNC_ALARM_FILENAME}"
        )

    def test_newest_device_wins_across_several(self) -> None:
        """The alarm set most recently wins, whatever order devices list in.

        This is the migration case: the phone's old "phone" directory still
        holds a stale alarm while its new uuid directory holds the current
        one. Ranking by HLC rather than listing order is what stops the PC
        waking at the abandoned time.
        """
        client = MagicMock()
        client.list_directory.return_value = ["new-uuid", "phone"]
        client.get_file_text.side_effect = lambda path: {
            f"{SYNC_DEVICES_PREFIX}/new-uuid/{SYNC_ALARM_FILENAME}": _log(
                5, 30, hlc="2026-08-09T10:00:00.000Z-0000-new-uuid"
            ),
            f"{SYNC_DEVICES_PREFIX}/phone/{SYNC_ALARM_FILENAME}": _log(
                9, 0, hlc="2026-07-01T10:00:00.000Z-0000-phone"
            ),
        }[path]
        with self._patched(client=client):
            fetched = _fetch_firebase_alarm()
            assert fetched is not None
            assert fetched[:2] == (5, 30)

    def test_falls_back_to_the_legacy_path_when_nothing_lists(self) -> None:
        """A backend that lists nothing still reads the un-migrated phone."""
        client = MagicMock()
        client.list_directory.return_value = ["phone"]
        client.get_file_text.side_effect = [None, _log(8, 5)]
        with self._patched(client=client):
            fetched = _fetch_firebase_alarm()
            assert fetched is not None
            assert fetched[:2] == (8, 5)
        assert client.get_file_text.call_args_list[-1].args[0] == SYNC_ALARM_PATH

    def test_a_device_publishing_garbage_does_not_win(self) -> None:
        """One unparsable device must not shadow a healthy one."""
        client = MagicMock()
        client.list_directory.return_value = ["broken", "good"]
        client.get_file_text.side_effect = lambda path: {
            f"{SYNC_DEVICES_PREFIX}/broken/{SYNC_ALARM_FILENAME}": "{not json",
            f"{SYNC_DEVICES_PREFIX}/good/{SYNC_ALARM_FILENAME}": _log(7, 20),
        }[path]
        with self._patched(client=client):
            fetched = _fetch_firebase_alarm()
            assert fetched is not None
            assert fetched[:2] == (7, 20)

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

        from wake_alarm import _sync_transport

        for name in (
            "crdt_sync",
            "crdt_sync._config",
            "crdt_sync._firebase_auth",
            "crdt_sync._remote",
        ):
            monkeypatch.setitem(sys.modules, name, None)
        try:
            reloaded = importlib.reload(_sync_transport)
            assert reloaded._FIREBASE_AVAILABLE is False
        finally:
            monkeypatch.undo()
            # Restore the real module for every later test: a reload left in
            # the import-failed state would silently disable Firebase for the
            # rest of the session.
            importlib.reload(_sync_transport)
