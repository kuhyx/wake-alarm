"""Tests for clearing a power-key inhibitor orphaned by a crashed alarm.

Split from ``test_inhibit.py`` for the 250-line cap. The header, including the
copied whole, minus ``test_inhibit.py``'s ``_no_stale_scan`` stub: these tests
exercise the *real* cleanup, and stubbing it out would make every one of them
assert nothing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from wake_alarm import _inhibit
from wake_alarm._constants import INHIBIT_WHO

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


class TestStaleCleanup:
    """Clearing an inhibitor orphaned by a crashed alarm."""

    def test_identifies_our_own_child(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """A pid is judged by its argv, never by a command-line pattern.

        The earlier ``pkill -f`` version matched the shell that had just typed
        the pattern and killed *it* -- substring matching is self-matching.
        """
        proc = tmp_path / "77"
        proc.mkdir()
        (proc / "cmdline").write_bytes(
            b"systemd-inhibit\x00--who=" + INHIBIT_WHO.encode() + b"\x00"
        )
        monkeypatch.setattr(
            _inhibit.pathlib, "Path", lambda *p: tmp_path / p[-2] / p[-1]
        )
        assert _inhibit._is_our_inhibitor("77") is True

    def test_ignores_a_pid_that_vanished(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """A process that exited between listing and reading is not stale."""
        monkeypatch.setattr(
            _inhibit.pathlib, "Path", lambda *p: tmp_path / "definitely-absent"
        )
        assert _inhibit._is_our_inhibitor("99") is False

    def test_kills_only_matching_pids(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Someone else's systemd-inhibit is left strictly alone."""
        monkeypatch.setattr(_inhibit.shutil, "which", lambda _name: "/usr/bin/pgrep")
        monkeypatch.setattr(
            _inhibit.subprocess,
            "run",
            lambda *a, **k: MagicMock(stdout=b"11\n22\n"),
        )
        monkeypatch.setattr(_inhibit, "_is_our_inhibitor", lambda pid: pid == "22")
        signalled: list[int] = []
        monkeypatch.setattr(
            _inhibit.os, "kill", lambda pid, _sig: signalled.append(pid)
        )
        assert _inhibit.kill_stale_inhibitors() == 1
        assert signalled == [22]

    def test_survives_a_pid_that_exits_mid_kill(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A race between listing and killing is not an error."""
        monkeypatch.setattr(_inhibit.shutil, "which", lambda _name: "/usr/bin/pgrep")
        monkeypatch.setattr(
            _inhibit.subprocess, "run", lambda *a, **k: MagicMock(stdout=b"11\n")
        )
        monkeypatch.setattr(_inhibit, "_is_our_inhibitor", lambda _pid: True)

        def gone(_pid: int, _sig: int) -> None:
            raise ProcessLookupError

        monkeypatch.setattr(_inhibit.os, "kill", gone)
        assert _inhibit.kill_stale_inhibitors() == 0

    def test_no_pgrep_means_no_scan(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Without pgrep the cleanup is skipped rather than guessed at."""
        monkeypatch.setattr(_inhibit.shutil, "which", lambda _name: None)
        assert _inhibit.kill_stale_inhibitors() == 0

    def test_pgrep_failure_is_survivable(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A failed scan must not stop the alarm from starting."""
        monkeypatch.setattr(_inhibit.shutil, "which", lambda _name: "/usr/bin/pgrep")

        def boom(*_a: object, **_k: object) -> None:
            msg = "nope"
            raise OSError(msg)

        monkeypatch.setattr(_inhibit.subprocess, "run", boom)
        with caplog.at_level("WARNING"):
            assert _inhibit.kill_stale_inhibitors() == 0
        assert "Could not check for a stale" in caplog.text
