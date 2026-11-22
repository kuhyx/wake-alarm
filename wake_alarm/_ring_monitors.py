"""The monitors' share of a PipeWire ring.

The night's speakers are switched off at the knob (2026-11-22), so a ring
must reach the two monitors too. PipeWire does not expose them (the NVidia
card's profile is off), but the active session's ACL lets this user open
their ALSA devices, so ``ring_alsa.sh --monitors`` plays to each one
directly, logging one ``ring_sink`` line per monitor to this unit's journal.
The script runs in its own session so :meth:`MonitorLoops.stop` can end
every ``aplay`` it started at once.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
import signal
import subprocess

_logger = logging.getLogger(__name__)

# Where install.sh puts scripts/pc/ring_alsa.sh.
RING_SCRIPT = Path("/usr/local/lib/wake-alarm/ring_alsa.sh")


def _spawn(cmd: list[str]) -> subprocess.Popen[bytes]:
    """Start ``cmd`` as its own process group; the seam tests replace."""
    return subprocess.Popen(cmd, start_new_session=True)


class MonitorLoops:
    """One ``ring_alsa.sh --monitors`` process group."""

    def __init__(self, proc: subprocess.Popen[bytes]) -> None:
        """Wrap a started group."""
        self._proc: subprocess.Popen[bytes] | None = proc

    @classmethod
    def start(cls, rise: Path, loop: Path) -> MonitorLoops | None:
        """Start the loops; None (logged) when they cannot start.

        Never fatal: the speakers' ring must not depend on the monitors.
        """
        try:
            proc = _spawn([str(RING_SCRIPT), "--monitors", str(rise), str(loop)])
        except OSError as exc:
            _logger.warning("Monitor ring not started: %s", exc)
            return None
        return cls(proc)

    def stop(self) -> None:
        """SIGTERM the whole group. Safe to call twice."""
        proc, self._proc = self._proc, None
        if proc is None or proc.poll() is not None:
            return
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
