"""Render the post-dismissal banner across every monitor.

Split out of ``_alarm.py`` for the 250-line cap. Pure presentation: deciding
*whether* a skip was earned stays in the alarm, this only draws the outcome.
"""

from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

    from gatelock import LockConfig

SKIP_EARNED_MESSAGE = "Workout skip earned! Enjoy your morning."
NO_SKIP_MESSAGE = "Alarm dismissed. No workout skip."

# How long the banner stays up before the lock closes itself.
BANNER_LINGER_MS = 3000


def clear_surfaces(containers: Iterable[tk.Misc]) -> None:
    """Remove every child widget from each per-output container.

    Args:
        containers: Per-output container widgets.
    """
    for container in containers:
        for widget in container.winfo_children():
            widget.destroy()


def show_dismissal(
    containers: Iterable[tk.Misc],
    config: LockConfig,
    *,
    earned_skip: bool,
) -> None:
    """Replace the challenge UI with the outcome message on every monitor.

    Args:
        containers: Per-output container widgets.
        config: Styling source for fonts, colours and spacing.
        earned_skip: Whether the workout skip was earned.
    """
    clear_surfaces(containers)
    message = SKIP_EARNED_MESSAGE if earned_skip else NO_SKIP_MESSAGE
    colour = config.success if earned_skip else config.warning
    for container in containers:
        tk.Label(
            container,
            text=message,
            font=config.font("display", bold=True),
            fg=colour,
            bg=config.bg,
        ).pack(pady=config.space("lg"))
