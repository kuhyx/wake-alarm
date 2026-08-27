"""Tests for the power-key inhibitor held while the alarm rings."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock

import pytest

from wake_alarm import _inhibit


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
            live = MagicMock(pid=4242)
            # Still running after the confirm wait: logind accepted it.
            live.wait.side_effect = subprocess.TimeoutExpired("systemd-inhibit", 0.5)
            return live

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

    def test_a_refused_inhibit_is_reported_as_none(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Claiming a block we did not get is worse than reporting none.

        Popen succeeding only means the *binary* launched. logind can still
        refuse -- polkit denies a non-interactive session outright, which a
        vmbox run turned up: systemd-inhibit printed "Failed to inhibit:
        Access denied" and exited 1 while the alarm logged the power key as
        blocked.
        """
        monkeypatch.setattr(
            _inhibit, "_systemd_inhibit_path", lambda: "/usr/bin/systemd-inhibit"
        )
        refused = MagicMock(returncode=1)
        refused.wait.return_value = 1
        refused.stderr.read.return_value = b"Failed to inhibit: Access denied"
        monkeypatch.setattr(_inhibit.subprocess, "Popen", lambda *a, **k: refused)
        with caplog.at_level("WARNING"):
            assert _inhibit.take_power_key_inhibitor() is None
        assert "logind refused" in caplog.text
        assert "Access denied" in caplog.text

    def test_a_refusal_with_no_stderr_still_reports(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A silent refusal is still a refusal, and still must not be claimed."""
        monkeypatch.setattr(
            _inhibit, "_systemd_inhibit_path", lambda: "/usr/bin/systemd-inhibit"
        )
        refused = MagicMock(returncode=1, stderr=None)
        refused.wait.return_value = 1
        monkeypatch.setattr(_inhibit.subprocess, "Popen", lambda *a, **k: refused)
        with caplog.at_level("WARNING"):
            assert _inhibit.take_power_key_inhibitor() is None
        assert "no detail" in caplog.text

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
