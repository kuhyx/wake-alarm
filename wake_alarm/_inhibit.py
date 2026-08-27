"""Hold a logind inhibitor so one power-button press cannot kill the alarm.

Item 2 of the hardening plan. Today a short press on the power button runs
``HandlePowerKey=poweroff`` and the alarm is gone in one tap -- less effort
than typing a single challenge round.

Verified on this host before writing any of this:

    $ grep PowerKey /etc/systemd/logind.conf
    #HandlePowerKey=poweroff
    #HandlePowerKeyLongPress=ignore
    #PowerKeyIgnoreInhibited=no

``PowerKeyIgnoreInhibited=no`` is the default and is in force, which is exactly
what makes a ``--mode=block`` inhibitor suppress the short press. So no
``logind.conf`` edit is needed, and none is made: a drop-in would change the
machine permanently, while an inhibitor is scoped to the alarm's lifetime.

**What this cannot block, stated plainly:** a ~4 second firmware hold cuts
power below the operating system, and so does the PSU switch. Neither is
defeatable from userspace. The durable defence against those is the fire-time
session record in :mod:`wake_alarm._alarm_session` -- the alarm re-fires on the
next boot rather than being escaped -- not this inhibitor.

**Why a bounded ``sleep`` and not ``sleep infinity``:** the inhibitor is a
child process. If the alarm dies without running ``on_close()`` -- a crash, a
SIGKILL -- an orphaned blocker holding ``handle-power-key`` would leave the
power button dead until the next reboot, which is a far worse failure than the
one being fixed. The child therefore exits on its own after
``INHIBIT_MAX_SECONDS`` even if nobody ever releases it, and a stale one from a
previous run is killed at startup -- by pid, via ``/proc``, never by matching a
command-line substring (see :func:`_is_our_inhibitor` for why).
"""

from __future__ import annotations

import logging
import os
import pathlib
import shutil
import signal
import subprocess

from wake_alarm._constants import (
    INHIBIT_MAX_SECONDS,
    INHIBIT_WHAT,
    INHIBIT_WHO,
    INHIBIT_WHY,
)

_logger = logging.getLogger(__name__)


def _systemd_inhibit_path() -> str | None:
    """Return the absolute path to systemd-inhibit, or None when absent."""
    return shutil.which("systemd-inhibit")


def _is_our_inhibitor(pid: str) -> bool:
    """Report whether *pid* is one of this alarm's inhibitor children.

    Reads the process's own argv rather than trusting a pattern match. This
    matters: an earlier version used ``pkill -f "--who=wake-alarm"``, which on
    a real run matched the *shell that had just typed that pattern* and killed
    it instead of the inhibitor. Matching a command line by substring is
    inherently self-matching; asking a specific pid what it is, is not.
    """
    try:
        argv = pathlib.Path("/proc", pid, "cmdline").read_bytes()
    except OSError:
        # The process exited between listing and reading -- it is not stale,
        # it is simply gone.
        return False
    return f"--who={INHIBIT_WHO}".encode() in argv


def kill_stale_inhibitors() -> int:
    """Kill any inhibitor left behind by an earlier alarm process.

    A blocker that outlived its alarm holds the power button down for every
    later session, so this runs before a new one is taken rather than trusting
    that the previous process exited cleanly.

    Matches on the exact process name and then confirms via ``/proc``, so it
    can only ever kill a real ``systemd-inhibit`` of ours.

    Returns:
        The number of stale processes signalled.
    """
    pgrep = shutil.which("pgrep")
    if pgrep is None:
        return 0
    try:
        listed = subprocess.run(
            [pgrep, "-x", "systemd-inhibit"],
            capture_output=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        _logger.warning("Could not check for a stale power-key inhibitor")
        return 0
    killed = 0
    for pid in listed.stdout.decode(errors="replace").split():
        if not _is_our_inhibitor(pid):
            continue
        try:
            os.kill(int(pid), signal.SIGTERM)
        except (OSError, ValueError):
            continue
        killed += 1
    if killed:
        _logger.warning(
            "Killed %d stale power-key inhibitor(s) left by an earlier alarm",
            killed,
            extra={"event": "inhibitor_stale_killed", "count": killed},
        )
    return killed


def take_power_key_inhibitor() -> subprocess.Popen[bytes] | None:
    """Block the power key for the alarm's lifetime.

    Returns:
        The inhibitor child process, or None when systemd-inhibit is missing
        or could not be started. A missing inhibitor never stops the alarm:
        being loud without the power key blocked beats not ringing at all.
    """
    inhibit = _systemd_inhibit_path()
    if inhibit is None:
        _logger.warning(
            "systemd-inhibit not on PATH; the power button can still kill "
            "the alarm in one press",
            extra={"event": "inhibitor_unavailable"},
        )
        return None
    kill_stale_inhibitors()
    cmd = [
        inhibit,
        f"--what={INHIBIT_WHAT}",
        "--mode=block",
        f"--who={INHIBIT_WHO}",
        f"--why={INHIBIT_WHY}",
        "sleep",
        str(int(INHIBIT_MAX_SECONDS)),
    ]
    try:
        # Deliberately not a context manager: this child must outlive the
        # call and is reaped by release_power_key_inhibitor().
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        _logger.warning(
            "Could not take the power-key inhibitor; the alarm rings unprotected",
            exc_info=True,
            extra={"event": "inhibitor_failed"},
        )
        return None
    _logger.warning(
        "Power key inhibited for up to %ds (pid %d) — a short press no longer "
        "kills the alarm; a ~4s firmware hold still cuts power",
        int(INHIBIT_MAX_SECONDS),
        process.pid,
        extra={"event": "inhibitor_taken", "pid": process.pid},
    )
    return process


def release_power_key_inhibitor(process: subprocess.Popen[bytes] | None) -> None:
    """Release the inhibitor taken by :func:`take_power_key_inhibitor`.

    Safe to call more than once and safe to call with None, because it runs
    from ``on_close()``, which itself runs on every exit path.

    Args:
        process: The inhibitor child, or None when one was never taken.
    """
    if process is None:
        return
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        _logger.warning("Power-key inhibitor ignored SIGTERM; killed it")
    _logger.info("Power key released", extra={"event": "inhibitor_released"})
