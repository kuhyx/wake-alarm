"""Tests for the power-key inhibitor held while the alarm rings."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from wake_alarm import _inhibit
from wake_alarm._constants import INHIBIT_WHO

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def _no_stale_scan(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub the stale scan, so taking an inhibitor never scans the real host.

    Not autouse: TestStaleCleanup exercises the real function, and an autouse
    stub would silently make every one of those tests assert nothing.
    """
    monkeypatch.setattr(_inhibit, "kill_stale_inhibitors", lambda: 0)


def test_resolves_systemd_inhibit_from_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The binary is looked up on PATH, never hardcoded."""
    monkeypatch.setattr(_inhibit.shutil, "which", lambda name: f"/usr/bin/{name}")
    assert _inhibit._systemd_inhibit_path() == "/usr/bin/systemd-inhibit"


@pytest.mark.usefixtures("_no_stale_scan")
class TestTakeInhibitor:
    """Taking the inhibitor that blocks the power button."""

    def test_spawns_a_blocking_inhibitor(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The child blocks handle-power-key and self-terminates."""
        monkeypatch.setattr(
            _inhibit, "_systemd_inhibit_path", lambda: "/usr/bin/systemd-inhibit"
        )
        captured: list[list[str]] = []

        def fake_popen(cmd: list[str], **_kwargs: object) -> MagicMock:
            captured.append(cmd)
            return MagicMock(pid=4242)

        monkeypatch.setattr(_inhibit.subprocess, "Popen", fake_popen)

        assert _inhibit.take_power_key_inhibitor() is not None

        cmd = captured[0]
        assert "--mode=block" in cmd
        assert "--what=handle-power-key:shutdown:idle" in cmd
        # Never `sleep infinity`: an orphaned blocker would hold the power
        # button down until the next reboot.
        assert cmd[-2] == "sleep"
        assert int(cmd[-1]) > 0

    def test_missing_binary_never_stops_the_alarm(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """No systemd-inhibit means an unprotected alarm, not no alarm."""
        monkeypatch.setattr(_inhibit, "_systemd_inhibit_path", lambda: None)
        with caplog.at_level("WARNING"):
            assert _inhibit.take_power_key_inhibitor() is None
        assert "systemd-inhibit not on PATH" in caplog.text

    def test_spawn_failure_is_survivable(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A failed spawn is logged and the alarm rings on."""
        monkeypatch.setattr(
            _inhibit, "_systemd_inhibit_path", lambda: "/usr/bin/systemd-inhibit"
        )

        def boom(_cmd: list[str], **_kwargs: object) -> MagicMock:
            msg = "no fork for you"
            raise OSError(msg)

        monkeypatch.setattr(_inhibit.subprocess, "Popen", boom)
        with caplog.at_level("WARNING"):
            assert _inhibit.take_power_key_inhibitor() is None
        assert "rings unprotected" in caplog.text

    def test_clears_a_stale_inhibitor_first(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A blocker from a crashed alarm is cleared before a new one is taken."""
        monkeypatch.setattr(
            _inhibit, "_systemd_inhibit_path", lambda: "/usr/bin/systemd-inhibit"
        )
        monkeypatch.setattr(_inhibit.subprocess, "Popen", lambda *a, **k: MagicMock())
        cleared: list[str] = []

        def fake_clear() -> int:
            cleared.append("cleared")
            return 0

        monkeypatch.setattr(_inhibit, "kill_stale_inhibitors", fake_clear)
        _inhibit.take_power_key_inhibitor()
        assert cleared == ["cleared"]


class TestReleaseInhibitor:
    """Releasing the inhibitor when the alarm ends."""

    def test_none_is_a_no_op(self) -> None:
        """on_close() runs on every path, including ones that took nothing."""
        _inhibit.release_power_key_inhibitor(None)

    def test_already_exited_is_a_no_op(self) -> None:
        """A child that self-terminated is not signalled again."""
        process = MagicMock()
        process.poll.return_value = 0
        _inhibit.release_power_key_inhibitor(process)
        process.terminate.assert_not_called()

    def test_terminates_a_live_inhibitor(self) -> None:
        """The ordinary path: SIGTERM, then reap."""
        process = MagicMock()
        process.poll.return_value = None
        _inhibit.release_power_key_inhibitor(process)
        process.terminate.assert_called_once_with()
        process.wait.assert_called_once_with(timeout=5)
        process.kill.assert_not_called()

    def test_kills_an_inhibitor_that_ignores_sigterm(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A stuck child must not outlive the alarm holding the power key."""
        process = MagicMock()
        process.poll.return_value = None
        process.wait.side_effect = subprocess.TimeoutExpired("systemd-inhibit", 5)
        with caplog.at_level("WARNING"):
            _inhibit.release_power_key_inhibitor(process)
        process.kill.assert_called_once_with()
        assert "ignored SIGTERM" in caplog.text


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
