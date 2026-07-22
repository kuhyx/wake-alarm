"""Widget construction for the wake alarm's dismiss-challenge screen."""

from __future__ import annotations

from dataclasses import dataclass
import tkinter as tk
from typing import TYPE_CHECKING

from wake_alarm._constants import DISMISS_ROUNDS_REQUIRED

if TYPE_CHECKING:
    from collections.abc import Callable

    from gatelock import LockConfig

    from wake_alarm._challenges import _Challenge


@dataclass
class _AlarmView:
    """The Tk widgets that make up the alarm's dismiss-challenge screen."""

    container: tk.Frame
    title_label: tk.Label
    round_label: tk.Label
    info_label: tk.Label
    code_label: tk.Label
    entry: tk.Entry
    status_label: tk.Label
    timer_label: tk.Label
    config: LockConfig


def _build_alarm_view(
    root: tk.Tk,
    challenge: _Challenge,
    config: LockConfig,
    on_submit: Callable[[object], None],
) -> _AlarmView:
    """Build the dismiss-challenge UI and return its widgets as a view."""
    container = tk.Frame(root, bg=config.bg)
    container.place(relx=0.5, rely=0.5, anchor="center")

    title_label = tk.Label(
        container,
        text="WAKE UP!",
        font=("Arial", 48, "bold"),
        fg=config.danger,
        bg=config.bg,
    )
    title_label.pack(pady=20)

    round_label = tk.Label(
        container,
        text=f"Round 1 / {DISMISS_ROUNDS_REQUIRED}",
        font=("Arial", 24, "bold"),
        fg=config.warning,
        bg=config.bg,
    )
    round_label.pack(pady=5)

    info_label = tk.Label(
        container,
        text=challenge.hint,
        font=("Arial", 18),
        fg=config.fg,
        bg=config.bg,
    )
    info_label.pack(pady=10)

    # Non-flash types use a smaller font because their display text is wider.
    code_font_size = (
        48 if challenge.kind in ("math", "sort", "sequence", "reverse") else 72
    )
    code_label = tk.Label(
        container,
        text=challenge.display,
        font=("Courier", code_font_size, "bold"),
        fg=config.success,
        bg=config.bg,
    )
    code_label.pack(pady=30)

    entry = tk.Entry(
        container,
        font=("Courier", 36),
        justify="center",
        width=12,
    )
    entry.pack(pady=10)
    entry.focus_set()
    entry.bind("<Return>", on_submit)

    status_label = tk.Label(
        container,
        text="",
        font=("Arial", 18),
        fg=config.danger,
        bg=config.bg,
    )
    status_label.pack(pady=10)

    timer_label = tk.Label(
        container,
        text="",
        font=("Arial", 14),
        fg=config.muted,
        bg=config.bg,
    )
    timer_label.pack(pady=5)

    return _AlarmView(
        container=container,
        title_label=title_label,
        round_label=round_label,
        info_label=info_label,
        code_label=code_label,
        entry=entry,
        status_label=status_label,
        timer_label=timer_label,
        config=config,
    )
