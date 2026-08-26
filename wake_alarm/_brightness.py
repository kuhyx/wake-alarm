"""Raise every monitor to full brightness when the alarm fires.

Split out of ``_audio.py`` for the 250-line cap; it is display control, not
audio, and only ever lived there for historical reasons.
"""

from __future__ import annotations

import logging
import shutil
import subprocess

_logger = logging.getLogger(__name__)


def _set_max_brightness() -> None:
    """Set all connected monitors to maximum brightness via xrandr."""
    xrandr = shutil.which("xrandr")
    if xrandr is None:
        _logger.warning("xrandr not on PATH; skipping max-brightness")
        return
    try:
        result = subprocess.run(
            [xrandr, "--query"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        _logger.warning("xrandr --query failed; skipping max-brightness", exc_info=True)
        return
    for line in result.stdout.splitlines():
        if " connected" in line:
            output = line.split()[0]
            try:
                subprocess.run(
                    [xrandr, "--output", output, "--brightness", "1.0"],
                    check=False,
                    capture_output=True,
                    timeout=5,
                )
            except (OSError, subprocess.TimeoutExpired):
                _logger.warning(
                    "Failed to set brightness on %s",
                    output,
                    exc_info=True,
                )
