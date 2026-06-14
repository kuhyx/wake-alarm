"""Display power and screensaver helpers for the wake alarm.

Wakes monitors that may be physically powered off (via DDC/CI) or in DPMS
standby, and restores the screensaver once the alarm dismiss flow ends.
"""

from __future__ import annotations

import logging
import shutil
import subprocess

_logger = logging.getLogger(__name__)


def _ddcutil_power_on() -> None:
    """Power on all connected monitors via DDC/CI VCP code D6.

    This wakes monitors that were physically turned off with the power button
    and therefore ignore DPMS signals.  Falls back silently when ddcutil is
    absent or returns an error (e.g. no i2c access yet).
    """
    ddcutil = shutil.which("ddcutil")
    if ddcutil is None:
        _logger.warning("ddcutil not on PATH; skipping DDC/CI monitor power-on")
        return
    try:
        result = subprocess.run(
            [ddcutil, "setvcp", "D6", "01"],
            check=False,
            capture_output=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        _logger.warning("ddcutil setvcp failed", exc_info=True)
        return
    if result.returncode != 0:
        _logger.warning(
            "ddcutil setvcp D6 01 exited %d: %s",
            result.returncode,
            result.stderr.decode(errors="replace").strip()[:200],
        )
    else:
        _logger.info("DDC/CI monitor power-on sent")


def _wake_display() -> None:
    """Force the display on and disable screensaver during alarm.

    Sends both a DDC/CI hard power-on (for monitors powered off via the
    power button) and a DPMS force-on (for monitors in standby).
    """
    _ddcutil_power_on()
    xset = shutil.which("xset")
    if xset is None:
        _logger.warning("xset not on PATH; skipping DPMS display wake")
        return
    for cmd in (
        [xset, "dpms", "force", "on"],
        [xset, "s", "off"],
    ):
        subprocess.run(cmd, check=False, capture_output=True, timeout=5)


def _restore_display() -> None:
    """Re-enable screensaver after the alarm ends."""
    xset = shutil.which("xset")
    if xset is None:
        _logger.warning("xset not on PATH; skipping display restore")
        return
    subprocess.run(
        [xset, "s", "on"],
        check=False,
        capture_output=True,
        timeout=5,
    )
