"""The PC reads the phone's alarm end-to-end encrypted, on both backends.

Real ``crdt_sync`` encryption over a dict-backed remote: the header, the
sealed records and the one-time copy of the old plaintext prefix are the
bytes a real backend would hold.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import patch

from crdt_sync import open_encrypted_client
import pytest

from wake_alarm import _sync_transport
from wake_alarm._constants import SYNC_DEVICES_PREFIX, SYNC_LEGACY_PREFIX
from wake_alarm.tests.conftest import TEST_ARGON2, TEST_PHRASE, DictStore

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

_HLC = "2026-11-12T05:00:00.000Z-0000-uuid1"


@pytest.fixture
def config_file(tmp_path: Path) -> Iterator[Path]:
    """This app's GitHub token config, redirected; no sibling fallbacks."""
    path = tmp_path / "sync.json"
    with (
        patch.object(_sync_transport, "SYNC_CONFIG_FILE", path),
        patch.object(_sync_transport, "SYNC_TOKEN_FALLBACK_FILES", ()),
    ):
        yield path


def _log(hour: int, minute: int, hlc: str = _HLC) -> str:
    return json.dumps(
        {
            "alarm": {
                "id": "alarm",
                "fields": {"alarm_hour": [hour, hlc], "alarm_minute": [minute, hlc]},
                "deleted": False,
            }
        }
    )


def _phone_publishes(store: DictStore, hour: int, minute: int) -> None:
    """What the updated phone app does: seal its log under the E2E prefix."""
    sealed, layout = open_encrypted_client(
        store, SYNC_LEGACY_PREFIX, passphrase=TEST_PHRASE, params=TEST_ARGON2
    )
    sealed.put_file_text(
        f"{layout.prefix}/uuid1/alarm.json", _log(hour, minute), message="t"
    )


def _firebase(store: DictStore, tmp_path: Path) -> object:
    config = tmp_path / "firebase.json"
    config.write_text("{}")
    return patch.multiple(
        "wake_alarm._sync_transport",
        FIREBASE_CONFIG_FILE=config,
        firebase_client_for=lambda _app: store,
    )


class TestFirebase:
    def test_reads_the_sealed_alarm(self, tmp_path: Path) -> None:
        store = DictStore()
        _phone_publishes(store, 6, 40)
        blob = store.files[f"{SYNC_DEVICES_PREFIX}/uuid1/alarm.json"]
        assert "alarm_hour" not in blob

        with _firebase(store, tmp_path):
            fetched = _sync_transport._fetch_firebase_alarm()

        assert fetched is not None
        assert fetched[:2] == (6, 40)

    def test_a_phone_not_yet_updated_is_copied_and_read(self, tmp_path: Path) -> None:
        old = f"{SYNC_LEGACY_PREFIX}/phone/alarm.json"
        store = DictStore({old: _log(7, 5)})

        with _firebase(store, tmp_path):
            fetched = _sync_transport._fetch_firebase_alarm()

        assert fetched is not None
        assert fetched[:2] == (7, 5)
        assert (
            "alarm_hour" not in store.files[f"{SYNC_DEVICES_PREFIX}/phone/alarm.json"]
        )
        assert store.files[old] == _log(7, 5)

    def test_no_passphrase_reads_nothing(self, tmp_path: Path) -> None:
        store = DictStore()
        _phone_publishes(store, 6, 40)
        with (
            _firebase(store, tmp_path),
            patch.object(_sync_transport, "PASSWORD_FILE", tmp_path / "gone"),
        ):
            assert _sync_transport.fetch_firebase_logs() is None

    def test_wrong_passphrase_reads_nothing(self, tmp_path: Path) -> None:
        store = DictStore()
        _phone_publishes(store, 6, 40)
        other = tmp_path / "other"
        other.write_text("not the passphrase")
        with (
            _firebase(store, tmp_path),
            patch.object(_sync_transport, "PASSWORD_FILE", other),
        ):
            assert _sync_transport.fetch_firebase_logs() is None

    def test_a_blob_under_another_key_is_skipped(self, tmp_path: Path) -> None:
        store = DictStore()
        _phone_publishes(store, 6, 40)
        alien = DictStore()
        _phone_publishes(alien, 9, 0)  # its own header, so its own key
        path = f"{SYNC_DEVICES_PREFIX}/uuid1/alarm.json"
        store.files[f"{SYNC_DEVICES_PREFIX}/stranger/alarm.json"] = alien.files[path]

        with _firebase(store, tmp_path):
            published = _sync_transport.fetch_firebase_logs()

        assert published is not None
        assert [device for device, _ in published] == ["uuid1"]


class TestGitHubMirror:
    def test_reads_the_sealed_alarm_through_the_contents_client(
        self, config_file: Path
    ) -> None:
        config_file.write_text(json.dumps({"token": "ghp_x"}))
        store = DictStore()
        _phone_publishes(store, 5, 55)
        with patch.object(
            _sync_transport, "GitHubSyncClient", return_value=store
        ) as client_cls:
            fetched = _sync_transport._fetch_github_alarm()
        assert fetched is not None
        assert fetched[:2] == (5, 55)
        assert client_cls.call_args.args[2] == "ghp_x"

    def test_locked_reads_nothing(self, config_file: Path, tmp_path: Path) -> None:
        config_file.write_text(json.dumps({"token": "ghp_x"}))
        store = DictStore()
        _phone_publishes(store, 5, 55)
        with (
            patch.object(_sync_transport, "GitHubSyncClient", return_value=store),
            patch.object(_sync_transport, "PASSWORD_FILE", tmp_path / "gone"),
        ):
            assert _sync_transport._fetch_github_alarm() is None

    def test_no_phone_header_reads_nothing_and_writes_nothing(
        self, config_file: Path
    ) -> None:
        config_file.write_text(json.dumps({"token": "ghp_x"}))
        store = DictStore()
        with patch.object(_sync_transport, "GitHubSyncClient", return_value=store):
            assert _sync_transport._fetch_github_alarm() is None
        assert store.puts == []

    def test_header_but_no_alarm_is_none(self, config_file: Path) -> None:
        config_file.write_text(json.dumps({"token": "ghp_x"}))
        store = DictStore()
        open_encrypted_client(
            store, SYNC_LEGACY_PREFIX, passphrase=TEST_PHRASE, params=TEST_ARGON2
        )
        with patch.object(_sync_transport, "GitHubSyncClient", return_value=store):
            assert _sync_transport._fetch_github_alarm() is None

    def test_without_crdt_sync_nothing_is_read(self) -> None:
        with patch.object(_sync_transport, "_FIREBASE_AVAILABLE", new=False):
            assert _sync_transport._fetch_github_alarm() is None
