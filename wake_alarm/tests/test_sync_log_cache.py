"""The offline-first fallback of every Firebase-log reader.

``fetch_firebase_logs`` caches its last success (``_sync_log_cache``) and
serves it when a fetch fails, so the field readers (``_weight``,
``_energy``, ...) answer with the newest known data while the network is
down. These tests pin that contract.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from crdt_sync import RemoteSyncError
import pytest

from wake_alarm import _sync_log_cache
from wake_alarm._sync_log_cache import (
    read_synced_logs_cache,
    write_synced_logs_cache,
)
from wake_alarm._sync_transport import fetch_firebase_logs, fetch_remote_alarm

if TYPE_CHECKING:
    from pathlib import Path
    from typing import NoReturn

_LOGS = [("device-a", '{"alarm": {}}')]


@pytest.fixture(autouse=True)
def _cache_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the cache at tmp for every test here; the autouse conftest
    redirect covers the rest of the suite."""
    monkeypatch.setattr(
        _sync_log_cache, "SYNC_LOGS_CACHE_FILE", tmp_path / "logs_cache.json"
    )


def test_write_then_read_roundtrip() -> None:
    write_synced_logs_cache(_LOGS)
    assert read_synced_logs_cache() == _LOGS


def test_read_missing_file_is_none() -> None:
    assert read_synced_logs_cache() is None


def test_read_corrupt_file_is_none() -> None:
    file = _sync_log_cache.SYNC_LOGS_CACHE_FILE
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text("not json")
    assert read_synced_logs_cache() is None


def test_read_wrong_shape_is_none() -> None:
    file = _sync_log_cache.SYNC_LOGS_CACHE_FILE
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps({"logs": [{"wrong": "shape"}]}))
    assert read_synced_logs_cache() is None


def test_read_cache_not_a_dict_is_none() -> None:
    file = _sync_log_cache.SYNC_LOGS_CACHE_FILE
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(["logs"]))
    assert read_synced_logs_cache() is None


def test_read_logs_not_a_list_is_none() -> None:
    file = _sync_log_cache.SYNC_LOGS_CACHE_FILE
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps({"logs": 5}))
    assert read_synced_logs_cache() is None


def test_read_empty_logs_is_none() -> None:
    file = _sync_log_cache.SYNC_LOGS_CACHE_FILE
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps({"logs": []}))
    assert read_synced_logs_cache() is None


def test_write_failure_is_swallowed() -> None:
    # The cache path is a directory, so write_text raises; the failure must
    # be swallowed, not crash the reader it protects.
    blocker = _sync_log_cache.SYNC_LOGS_CACHE_FILE
    blocker.parent.mkdir(parents=True, exist_ok=True)
    blocker.mkdir()
    write_synced_logs_cache(_LOGS)  # must not raise


def _configured_transport(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A transport that *is* configured: the fetch reaches the backend."""
    config = tmp_path / "firebase-config.json"
    config.write_text("{}")
    monkeypatch.setattr("wake_alarm._sync_transport.FIREBASE_CONFIG_FILE", config)
    monkeypatch.setattr(
        "wake_alarm._sync_transport.firebase_client_for", lambda _app: object()
    )


def test_failed_fetch_serves_the_cache(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configured_transport(monkeypatch, tmp_path)
    write_synced_logs_cache(_LOGS)

    def _fail(_client: object) -> NoReturn:
        msg = "offline"
        raise RemoteSyncError(msg)

    monkeypatch.setattr("wake_alarm._sync_transport._read_published", _fail)
    assert fetch_firebase_logs(offline_cache=True) == _LOGS
    # Callers that did not ask (alarm path, audit, fallback ring) still see
    # the failure: stale logs must not pass for a live read there.
    assert fetch_firebase_logs() is None


def test_a_log_cache_does_not_skip_the_github_alarm_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configured_transport(monkeypatch, tmp_path)
    write_synced_logs_cache(_LOGS)

    def _fail(_client: object) -> NoReturn:
        msg = "offline"
        raise RemoteSyncError(msg)

    monkeypatch.setattr("wake_alarm._sync_transport._read_published", _fail)
    monkeypatch.setattr(
        "wake_alarm._sync_transport._fetch_github_alarm", lambda: (6, 30, None)
    )
    assert fetch_remote_alarm() == (6, 30, None)


def test_unconfigured_fetch_without_cache_is_none(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Conftest default: the config file does not exist, no cache written.
    assert fetch_firebase_logs() is None


def test_success_writes_the_cache(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configured_transport(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "wake_alarm._sync_transport._read_published", lambda _client: _LOGS
    )
    assert fetch_firebase_logs() == _LOGS
    assert read_synced_logs_cache() == _LOGS


def test_an_empty_fetch_returns_none_and_keeps_the_cache(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # An empty *successful* fetch (no devices, no exception) means "nothing
    # is published right now", not "the last value is still live". Serving
    # the old cache here would resurrect a phone that deliberately cleared
    # its alarm, so the fetch returns None and leaves the cache untouched.
    _configured_transport(monkeypatch, tmp_path)
    write_synced_logs_cache(_LOGS)
    monkeypatch.setattr(
        "wake_alarm._sync_transport._read_published", lambda _client: []
    )
    assert fetch_firebase_logs() is None
    assert read_synced_logs_cache() == _LOGS


def test_weight_offline_comes_from_the_cache(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # The reader half of offline-first: with the network down, the newest
    # known weigh-in is still the one last synced, not "none".
    _configured_transport(monkeypatch, tmp_path)
    log = json.dumps(
        {
            "alarm": {
                "fields": {
                    "latest_weight_kg": [
                        {"date": "2026-11-26", "kg": 81.5},
                        "2026-11-26T07:00:00.000Z-0-device-a",
                    ]
                }
            }
        }
    )
    write_synced_logs_cache([("device-a", log)])

    def _fail(_client: object) -> NoReturn:
        msg = "offline"
        raise RemoteSyncError(msg)

    monkeypatch.setattr("wake_alarm._sync_transport._read_published", _fail)
    from wake_alarm._weight import latest_weight

    weight = latest_weight()
    assert weight is not None
    assert (weight.date, weight.kg) == ("2026-11-26", 81.5)
