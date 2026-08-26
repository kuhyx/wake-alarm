"""Present a dismiss challenge and judge the answer.

Split out of ``_alarm.py`` for the 250-line cap. Everything here manipulates
the view for one round; the alarm keeps ownership of *how many* rounds are
needed and what happens when they are all done.
"""

from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING

from wake_alarm._countdown import (
    NO_SKIP_STATUS,
    WINDOW_CLOSED_INFO,
    countdown_text,
    refresh_interval_ms,
    remaining_seconds,
    skip_window_ms,
    skip_window_seconds,
)
from wake_alarm._dismiss_view import BANNER_LINGER_MS, show_dismissal
from wake_alarm._screen_flash import FLASH_PERIOD_MS, apply_flash_colour

__all__ = [
    "BANNER_LINGER_MS",
    "FLASH_PERIOD_MS",
    "NO_SKIP_STATUS",
    "WINDOW_CLOSED_INFO",
    "apply_flash_colour",
    "countdown_text",
    "hide_flash_code",
    "normalise",
    "refresh_interval_ms",
    "remaining_seconds",
    "show_challenge",
    "show_dismissal",
    "show_flash_countdown",
    "show_round_progress",
    "show_wrong_answer",
    "skip_window_ms",
    "skip_window_seconds",
]

if TYPE_CHECKING:
    from wake_alarm._alarm_view import _ViewGroup
    from wake_alarm._challenges import _Challenge


def normalise(entered: str) -> str:
    """Canonicalise typed input before comparison.

    Args:
        entered: Raw contents of the entry widget.

    Returns:
        Trimmed, upper-cased text.
    """
    return entered.strip().upper()


def show_challenge(view: _ViewGroup, challenge: _Challenge) -> None:
    """Display *challenge* and clear the entry ready for the answer.

    Args:
        view: The multi-monitor view group.
        challenge: The challenge to present.
    """
    view.code_label.configure(text=challenge.display, fg=view.config.success)
    view.info_label.configure(text=challenge.hint)
    view.entry.delete(0, tk.END)


def show_wrong_answer(view: _ViewGroup, challenge: _Challenge) -> None:
    """Report an incorrect answer and re-present the same challenge.

    Args:
        view: The multi-monitor view group.
        challenge: The challenge that was answered incorrectly.
    """
    view.status_label.configure(text="Wrong! Try again.")
    view.entry.delete(0, tk.END)
    if challenge.kind == "flash":
        view.code_label.configure(text=challenge.display, fg=view.config.success)


def show_flash_countdown(view: _ViewGroup, remaining: int) -> None:
    """Show how long the flash challenge stays visible.

    Args:
        view: The multi-monitor view group.
        remaining: Seconds before the code is hidden.
    """
    view.status_label.configure(text=f"Memorise! Hiding in {remaining}s…")


def hide_flash_code(view: _ViewGroup, challenge: _Challenge) -> None:
    """Mask the flash code and prompt for it from memory.

    Args:
        view: The multi-monitor view group.
        challenge: The challenge whose display is being hidden.
    """
    view.code_label.configure(
        text="?" * len(challenge.display),
        fg=view.config.muted,
    )
    view.status_label.configure(text="Now type the code from memory!")


def show_round_progress(view: _ViewGroup, *, completed: int, required: int) -> None:
    """Update the round counter and the encouragement line.

    Args:
        view: The multi-monitor view group.
        completed: How many rounds are done.
        required: How many rounds are needed in total.
    """
    view.round_label.configure(text=f"Round {completed + 1} / {required}")
    view.status_label.configure(text=f"Round {completed} done — keep going!")
