"""Make the PC's speakers ring: user PipeWire, or a root ALSA unit.

Two backends, chosen per ring by :func:`select_backend`:

* **PipeWire** -- an active graphical session on seat0 belongs to this user,
  so its PipeWire is reachable: unmute and max the default sink with
  ``wpctl`` and play with ``pw-play``.
* **ALSA unit** -- anything else (the night lockdown: lightdm masked, nobody
  logged in, and the user is not in ``audio``): start the root system unit
  ``wake-alarm-ring-alsa.service`` through its NOPASSWD sudoers entry. The
  unit plays straight to the speakers' card and has its own runtime cap.

Every process this module starts goes through ``_run`` / ``_popen``, the
seams the test suite replaces so a test can never make this host ring.
"""

from __future__ import annotations

import logging
import os
import subprocess
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from pathlib import Path

_logger = logging.getLogger(__name__)

ALSA_UNIT = "wake-alarm-ring-alsa.service"
_GRAPHICAL_TYPES = frozenset({"x11", "wayland"})
_COMMAND_TIMEOUT = 15.0


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    """Run ``cmd`` to completion; the seam tests replace."""
    return subprocess.run(
        cmd, check=False, capture_output=True, text=True, timeout=_COMMAND_TIMEOUT
    )


def _popen(cmd: list[str]) -> subprocess.Popen[bytes]:
    """Start ``cmd`` in the background; the seam tests replace."""
    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _ok(cmd: list[str]) -> tuple[bool, str]:
    """Run ``cmd``; ``(succeeded, output or error)``."""
    try:
        result = _run(cmd)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)
    output = (result.stdout or "").strip() or (result.stderr or "").strip()
    return result.returncode == 0, output


def _properties(text: str) -> dict[str, str]:
    """``Key=Value`` lines as a dict."""
    pairs = (line.partition("=") for line in text.splitlines())
    return {key: value for key, sep, value in pairs if sep}


def graphical_session() -> tuple[bool, str]:
    """Whether seat0's active session is this user's graphical one, and why."""
    ok, out = _ok(["loginctl", "show-seat", "seat0", "-p", "ActiveSession"])
    session = _properties(out).get("ActiveSession", "") if ok else ""
    if not session:
        return False, f"no active session on seat0 ({out or 'empty'})"
    ok, out = _ok(
        [
            "loginctl",
            "show-session",
            session,
            "-p",
            "Type",
            "-p",
            "Active",
            "-p",
            "User",
        ]
    )
    props = _properties(out) if ok else {}
    owner = props.get("User", "")
    if props.get("Type") not in _GRAPHICAL_TYPES or props.get("Active") != "yes":
        return False, f"seat0 session {session} is not an active graphical one"
    if owner != str(os.getuid()):
        return False, f"seat0 session {session} belongs to uid {owner or '?'}"
    return True, f"active {props['Type']} session {session} on seat0"


class Backend(Protocol):
    """One way of making noise."""

    name: str

    def start(self) -> tuple[bool, str]:
        """Begin ringing; ``(started, detail)``."""

    def pump(self) -> bool:
        """Keep the sound going; False when the backend has failed."""

    def stop(self) -> None:
        """Silence it. Must be safe to call twice."""


class PipeWireBackend:
    """``wpctl`` to unmute/max the default sink, ``pw-play`` rise then loop."""

    name = "pipewire"

    def __init__(self, rise: Path, loop: Path) -> None:
        """Play ``rise`` once, then ``loop`` forever."""
        self._rise, self._loop = rise, loop
        self._proc: subprocess.Popen[bytes] | None = None

    def _play(self, path: Path) -> None:
        """Start ``pw-play`` on ``path`` at full stream volume."""
        self._proc = _popen(["pw-play", "--volume", "1.0", str(path)])

    def start(self) -> tuple[bool, str]:
        """Unmute and max the sink, then play the rise."""
        for cmd in (
            ["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "0"],
            ["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "1.0"],
        ):
            ok, out = _ok(cmd)
            if not ok:
                return False, f"{' '.join(cmd)} failed: {out}"
        try:
            self._play(self._rise)
        except OSError as exc:
            return False, f"pw-play failed: {exc}"
        return True, "pw-play started"

    def pump(self) -> bool:
        """Restart the loop when a play ends; False when ``pw-play`` errored."""
        if self._proc is None:
            return False
        code = self._proc.poll()
        if code is None:
            return True
        if code != 0:
            _logger.warning("pw-play exited with %d", code)
            return False
        try:
            self._play(self._loop)
        except OSError:
            return False
        return True

    def stop(self) -> None:
        """Terminate the current ``pw-play``."""
        proc, self._proc = self._proc, None
        if proc is None or proc.poll() is not None:
            return
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


class AlsaUnitBackend:
    """The root unit; ``sudo -n systemctl start|stop``."""

    name = "alsa"

    def __init__(self) -> None:
        """Nothing is running until :meth:`start`."""
        self._started = False

    def start(self) -> tuple[bool, str]:
        """Start the unit through its NOPASSWD sudoers entry."""
        ok, out = _ok(["sudo", "-n", "systemctl", "start", ALSA_UNIT])
        self._started = ok
        return ok, "unit started" if ok else f"sudo systemctl start failed: {out}"

    def pump(self) -> bool:
        """The unit loops on its own."""
        return self._started

    def stop(self) -> None:
        """Stop the unit; logged, never raised, on failure."""
        if not self._started:
            return
        self._started = False
        ok, out = _ok(["sudo", "-n", "systemctl", "stop", ALSA_UNIT])
        if not ok:
            _logger.warning("Could not stop %s: %s", ALSA_UNIT, out)


def select_backend(rise: Path, loop: Path) -> tuple[Backend, str]:
    """PipeWire when seat0 has this user's graphical session, else ALSA."""
    graphical, why = graphical_session()
    if graphical:
        return PipeWireBackend(rise, loop), why
    return AlsaUnitBackend(), why
