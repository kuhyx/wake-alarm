"""The monitor loops beside the PipeWire ring, with every process faked."""

from __future__ import annotations

from pathlib import Path
import signal
import subprocess
from unittest.mock import MagicMock, patch

from wake_alarm import _ring_monitors, _ring_player
from wake_alarm._ring_monitors import RING_SCRIPT, MonitorLoops
from wake_alarm._ring_player import PipeWireBackend

# Bound at import, before conftest swaps the seam for a raiser.
REAL_SPAWN = _ring_monitors._spawn


def _done() -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], 0, stdout="", stderr="")


class TestMonitorLoops:
    def test_start_runs_the_script_in_monitors_mode(self) -> None:
        proc = MagicMock()
        with patch.object(_ring_monitors, "_spawn", return_value=proc) as spawn:
            loops = MonitorLoops.start(Path("rise.wav"), Path("loop.wav"))
        assert spawn.call_args.args[0] == [
            str(RING_SCRIPT),
            "--monitors",
            "rise.wav",
            "loop.wav",
        ]
        assert loops is not None

    def test_a_missing_script_never_fails_the_ring(self) -> None:
        with patch.object(_ring_monitors, "_spawn", side_effect=OSError("enoent")):
            assert MonitorLoops.start(Path("r"), Path("l")) is None

    def test_stop_signals_the_whole_group_once(self) -> None:
        proc = MagicMock(pid=4242)
        proc.poll.return_value = None
        loops = MonitorLoops(proc)
        with patch.object(_ring_monitors.os, "killpg") as killpg:
            loops.stop()
            proc.poll.return_value = 0
            loops.stop()
        killpg.assert_called_once_with(4242, signal.SIGTERM)

    def test_stop_ignores_a_group_already_gone(self) -> None:
        proc = MagicMock(pid=4242)
        proc.poll.return_value = None
        with patch.object(_ring_monitors.os, "killpg", side_effect=ProcessLookupError):
            MonitorLoops(proc).stop()

    def test_real_seam_starts_its_own_session(self) -> None:
        with patch.object(subprocess, "Popen") as popen:
            REAL_SPAWN(["x"])
        assert popen.call_args.kwargs["start_new_session"] is True


class TestPipeWireRingsTheMonitors:
    def test_start_and_stop_drive_the_monitor_loops(self) -> None:
        loops = MagicMock()
        backend = PipeWireBackend(Path("rise.wav"), Path("loop.wav"))
        with (
            patch.object(_ring_player, "_run", return_value=_done()),
            patch.object(_ring_player, "_popen", return_value=MagicMock()),
            patch.object(_ring_player.MonitorLoops, "start", return_value=loops) as st,
        ):
            assert backend.start()[0]
        st.assert_called_once_with(Path("rise.wav"), Path("loop.wav"))
        backend.stop()
        backend.stop()
        loops.stop.assert_called_once()
