"""Backend choice and the two backends, with every process faked."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from wake_alarm import _ring_player
from wake_alarm._ring_player import (
    ALSA_UNIT,
    AlsaUnitBackend,
    PipeWireBackend,
    graphical_session,
    select_backend,
)

if TYPE_CHECKING:
    from collections.abc import Callable

# Bound at import, before conftest swaps the seams for raisers.
REAL_RUN = _ring_player._run
REAL_POPEN = _ring_player._popen
UID = str(os.getuid())


def _done(stdout: str = "", code: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], code, stdout=stdout, stderr="")


def _loginctl(
    session: str, props: str
) -> Callable[[list[str]], subprocess.CompletedProcess[str]]:
    def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        if cmd[1] == "show-seat":
            return _done(f"ActiveSession={session}\n")
        return _done(props)

    return run


class TestGraphicalSession:
    def test_this_users_active_x11_session(self) -> None:
        run = _loginctl("7", f"Type=x11\nActive=yes\nUser={UID}\n")
        with patch.object(_ring_player, "_run", run):
            ok, why = graphical_session()
        assert ok
        assert "x11 session 7" in why

    @pytest.mark.parametrize(
        ("props", "expected"),
        [
            (f"Type=tty\nActive=yes\nUser={UID}\n", "not an active graphical"),
            (f"Type=wayland\nActive=no\nUser={UID}\n", "not an active graphical"),
            ("Type=x11\nActive=yes\nUser=0\n", "belongs to uid 0"),
            ("Type=x11\nActive=yes\n", "belongs to uid ?"),
        ],
    )
    def test_anything_else_is_not_ours(self, props: str, expected: str) -> None:
        with patch.object(_ring_player, "_run", _loginctl("7", props)):
            ok, why = graphical_session()
        assert not ok
        assert expected in why

    def test_no_active_session(self) -> None:
        with patch.object(_ring_player, "_run", _loginctl("", "")):
            ok, why = graphical_session()
        assert not ok
        assert "no active session" in why

    def test_loginctl_missing(self) -> None:
        with patch.object(_ring_player, "_run", side_effect=OSError("nope")):
            ok, why = graphical_session()
        assert not ok
        assert "nope" in why

    def test_select_backend(self) -> None:
        with patch.object(_ring_player, "graphical_session", return_value=(True, "g")):
            backend, why = select_backend(Path("r"), Path("l"))
        assert (backend.name, why) == ("pipewire", "g")
        with patch.object(_ring_player, "graphical_session", return_value=(False, "n")):
            backend, why = select_backend(Path("r"), Path("l"))
        assert (backend.name, why) == ("alsa", "n")


class TestPipeWire:
    def _backend(self) -> PipeWireBackend:
        return PipeWireBackend(Path("rise.wav"), Path("loop.wav"))

    def test_start_unmutes_maxes_and_plays_the_rise(self) -> None:
        run = MagicMock(return_value=_done())
        proc = MagicMock()
        with (
            patch.object(_ring_player, "_run", run),
            patch.object(_ring_player, "_popen", return_value=proc) as popen,
        ):
            assert self._backend().start() == (True, "pw-play started")
        assert [c.args[0][1] for c in run.call_args_list] == ["set-mute", "set-volume"]
        assert popen.call_args.args[0] == ["pw-play", "--volume", "1.0", "rise.wav"]

    def test_start_fails_when_wpctl_fails(self) -> None:
        with patch.object(_ring_player, "_run", return_value=_done("no sink", 1)):
            ok, detail = self._backend().start()
        assert not ok
        assert "no sink" in detail

    def test_start_fails_when_pw_play_is_missing(self) -> None:
        with (
            patch.object(_ring_player, "_run", return_value=_done()),
            patch.object(_ring_player, "_popen", side_effect=OSError("enoent")),
        ):
            ok, detail = self._backend().start()
        assert not ok
        assert "enoent" in detail

    def test_pump_loops_after_the_rise_and_reports_failure(self) -> None:
        backend = self._backend()
        assert not backend.pump()  # never started
        playing, finished, errored = MagicMock(), MagicMock(), MagicMock()
        playing.poll.return_value = None
        finished.poll.return_value = 0
        errored.poll.return_value = 1
        with patch.object(_ring_player, "_popen", return_value=playing) as popen:
            backend._proc = playing
            assert backend.pump()
            backend._proc = finished
            assert backend.pump()
        assert popen.call_args.args[0][-1] == "loop.wav"
        backend._proc = errored
        assert not backend.pump()
        backend._proc = finished
        with patch.object(_ring_player, "_popen", side_effect=OSError("gone")):
            assert not backend.pump()

    def test_stop_terminates_and_kills_if_needed(self) -> None:
        backend = self._backend()
        backend.stop()  # nothing running
        proc = MagicMock()
        proc.poll.return_value = None
        proc.wait.side_effect = subprocess.TimeoutExpired("pw-play", 5)
        backend._proc = proc
        backend.stop()
        proc.terminate.assert_called_once()
        proc.kill.assert_called_once()
        done = MagicMock()
        done.poll.return_value = 0
        backend._proc = done
        backend.stop()
        done.terminate.assert_not_called()


class TestAlsaUnit:
    def test_start_pump_stop(self) -> None:
        run = MagicMock(return_value=_done())
        backend = AlsaUnitBackend()
        backend.stop()  # not started: no sudo call
        with patch.object(_ring_player, "_run", run):
            assert backend.start() == (True, "unit started")
            assert backend.pump()
            backend.stop()
            backend.stop()
        assert [c.args[0] for c in run.call_args_list] == [
            ["sudo", "-n", "systemctl", "start", ALSA_UNIT],
            ["sudo", "-n", "systemctl", "stop", ALSA_UNIT],
        ]

    def test_start_failure_and_stop_failure(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        backend = AlsaUnitBackend()
        with patch.object(_ring_player, "_run", return_value=_done("denied", 1)):
            ok, detail = backend.start()
            assert not ok
            assert "denied" in detail
            assert not backend.pump()
            backend._started = True
            backend.stop()
        assert "Could not stop" in caplog.text


def test_real_seams_call_subprocess() -> None:
    with (
        patch.object(subprocess, "run", return_value=_done("x")) as run,
        patch.object(subprocess, "Popen") as popen,
    ):
        assert REAL_RUN(["loginctl"]).stdout == "x"
        REAL_POPEN(["pw-play", "x.wav"])
    assert run.call_args.args[0] == ["loginctl"]
    assert popen.call_args.args[0] == ["pw-play", "x.wav"]
