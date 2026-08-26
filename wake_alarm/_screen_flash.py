"""Alternate the lock screen's background colour to hold attention.

Split out of ``_alarm.py`` for the 250-line cap. The 750 ms period is
deliberate: it is ~1.3 Hz, comfortably under the ~3 Hz threshold associated
with photosensitive seizures. Do not shorten it to make the alarm "more
urgent" -- the escalating audio is the right lever for that.
"""

from __future__ import annotations

import contextlib
import tkinter as tk
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

# Milliseconds between colour swaps. ~1.3 Hz; see the module docstring.
FLASH_PERIOD_MS = 750


def apply_flash_colour(
    root: tk.Tk,
    containers: Iterable[tk.Frame],
    colour: str,
) -> None:
    """Paint *colour* onto the backdrop and every per-output surface.

    The surfaces sit on top of the root backdrop, so recolouring only the root
    would be invisible on every monitor.

    Args:
        root: The root window holding the backdrop.
        containers: Per-output container widgets.
        colour: The background colour to apply.
    """
    root.configure(bg=colour)
    for container in containers:
        # A surface torn down mid-flash must not stop the others repainting.
        with contextlib.suppress(tk.TclError):
            container.configure(bg=colour)
            container.winfo_toplevel().configure(bg=colour)
