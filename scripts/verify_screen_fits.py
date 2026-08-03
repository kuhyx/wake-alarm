#!/usr/bin/env python3
"""Assert the alarm's screens fit a 1366x768 display.

The alarm ``place``s a centred frame, and a ``place``d frame takes its
*requested* size: when it is taller than the screen the parent shears equal
amounts off the top **and** the bottom -- which here means losing "WAKE UP!"
and the answer entry at once, on a screen whose entire purpose is to be
answered before it will stop. There is no scrollbar and nothing to indicate
anything is missing, so "it fits" is the only thing keeping it usable.

Runs the real builders against a real (throwaway) X display, because widget
heights come from the font engine and nothing short of rendering can answer
this honestly:

    cd ~/wake-alarm && python3 -m scripts.verify_screen_fits

Run as a *module*, not a path: ``-m`` puts the repo root on
``sys.path`` so ``wake_alarm`` resolves from the checkout. Running it as a
path only works where the package happens to be pip-installed, which is
why it passed locally and died in CI.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tkinter as tk
from typing import TYPE_CHECKING

from gatelock import LockConfig, measure_fit, report_fit

from wake_alarm._alarm_view import _build_alarm_view
from wake_alarm._challenges import (
    _make_flash_challenge,
    _make_math_challenge,
    _make_reverse_challenge,
    _make_sequence_challenge,
    _make_sort_challenge,
)
from wake_alarm._escape_flow import EscapeCallbacks, EscapeDialog, build_tracker

if TYPE_CHECKING:
    from collections.abc import Callable

    from gatelock import FitResult, ScrollableSurface

_logger = logging.getLogger(__name__)

INNER_ENV = "_SCREEN_FITS_CHECK_INNER"

# The panel this app has to fit: the machine it runs on.
WIDTH = 1366
HEIGHT = 768


def reexec_under_xvfb() -> int:
    """Re-run this script on a throwaway X display, returning its exit code."""
    xvfb_run = shutil.which("xvfb-run")
    if xvfb_run is None:
        _logger.error(
            "xvfb-run not found. Install it with: sudo pacman -S --needed "
            "xorg-server-xvfb"
        )
        return 1
    env = dict(os.environ, **{INNER_ENV: "1"})
    return subprocess.run(
        [
            xvfb_run,
            "-a",
            # Bigger than the size under test, so the surface is sized by the
            # geometry the harness sets rather than clamped by the display.
            "-s",
            "-screen 0 1600x1200x24",
            sys.executable,
            "-m",
            "scripts.verify_screen_fits",
        ],
        check=False,
        cwd=Path(__file__).resolve().parent.parent,
        env=env,
    ).returncode


def _placed_child(parent: tk.Misc) -> tk.Misc:
    """Return the ``place``d descendant that carries the screen's height.

    ``place`` does not propagate a child's size to its parent, so measuring
    the parent would report an empty screen. Falls back to the parent itself
    when nothing is placed, which measures correctly for packed layouts.
    """
    for child in parent.winfo_children():
        if child.winfo_manager() == "place":
            return child
        found = _placed_child(child)
        if found is not child:
            return found
    return parent


# Every challenge kind, not a random one: the flash kind renders its code at
# 2.25x the display token where the others use 1.5x, and the sequence kind's
# display string is the longest. A hook that picked one at random would pass
# or fail by dice roll -- which is worse than no hook.
_CHALLENGE_KINDS = (
    ("math", _make_math_challenge),
    ("flash", _make_flash_challenge),
    ("sort", _make_sort_challenge),
    ("sequence", _make_sequence_challenge),
    ("reverse", _make_reverse_challenge),
)


def _build_alarm(surface: ScrollableSurface, make: Callable[[], object]) -> tk.Misc:
    """Paint one dismiss challenge and return the frame to measure."""
    _build_alarm_view(
        surface.content,
        make(),
        LockConfig(),
        on_submit=lambda _event: None,
        entry_var=tk.StringVar(master=surface.content),
    )
    return _placed_child(surface.content)


def _build_escape(surface: ScrollableSurface) -> tk.Misc:
    """Paint the escape-hatch form and return the frame to measure."""
    dialog = EscapeDialog(
        surface.content,
        LockConfig(),
        build_tracker(),
        EscapeCallbacks(on_granted=lambda: None, on_cancel=lambda: None),
    )
    dialog.frame.pack()
    return dialog.frame


def measure_all() -> list[FitResult]:
    """Measure every screen at the supported size."""
    results = [
        measure_fit(
            f"dismiss-challenge:{kind}",
            lambda surface, make=make: _build_alarm(surface, make),
            width=WIDTH,
            height=HEIGHT,
        )
        for kind, make in _CHALLENGE_KINDS
    ]
    results.append(
        measure_fit("escape-hatch", _build_escape, width=WIDTH, height=HEIGHT)
    )
    return results


def main() -> int:
    """Measure every screen and fail if any of them overflows."""
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    if os.environ.get(INNER_ENV) != "1":
        return reexec_under_xvfb()

    _logger.info("Measuring every alarm screen against a %dx%d panel:", WIDTH, HEIGHT)
    if report_fit(measure_all()):
        _logger.info("\nOK: every screen fits.")
        return 0
    _logger.error(
        "\nAt least one screen is taller than the display. A place-centred "
        "surface clips at BOTH edges when that happens, so the overflow is "
        "not merely hidden -- it is unrecoverable."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
