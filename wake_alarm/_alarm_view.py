"""Widget construction for the wake alarm's dismiss-challenge screen."""

from __future__ import annotations

from dataclasses import dataclass
import tkinter as tk
from typing import TYPE_CHECKING

from gatelock import bind_activate

from wake_alarm._constants import DISMISS_ROUNDS_REQUIRED
from wake_alarm._view_proxies import _EntryProxy, _LabelProxy, _ViewGroup

# Re-imported so existing references keep resolving; __all__ stops ruff
# deleting them as unused.
__all__ = ["_EntryProxy", "_LabelProxy", "_ViewGroup"]

if TYPE_CHECKING:
    from collections.abc import Callable

    from gatelock import LockConfig

    from wake_alarm._challenges import _Challenge


@dataclass
class _AlarmLabels:
    """Every label on one monitor's challenge screen.

    Grouped rather than spread across :class:`_AlarmView` so that fanning a
    ``configure`` call out by name (see :meth:`_ViewGroup._label`) has one
    obvious namespace to look in.
    """

    title: tk.Label
    round_counter: tk.Label
    info: tk.Label
    code: tk.Label
    status: tk.Label
    timer: tk.Label


@dataclass
class _AlarmView:
    """The Tk widgets that make up the alarm's dismiss-challenge screen.

    ``container`` is placed and never unpacked; ``challenge_frame`` holds
    everything the escape hatch has to take off the screen while its form is
    up, so hiding and restoring the challenge is one call each way rather
    than a per-widget ``pack_forget`` that cannot be undone.
    """

    container: tk.Frame
    challenge_frame: tk.Frame
    labels: _AlarmLabels
    entry: tk.Entry
    escape_button: tk.Button
    config: LockConfig
    output_name: str = ""


def _build_challenge(
    parent: tk.Misc,
    challenge: _Challenge,
    config: LockConfig,
    on_submit: Callable[[object], None],
    entry_var: tk.StringVar,
) -> tuple[_AlarmLabels, tk.Entry]:
    """Fill ``parent`` with the challenge itself, top to bottom.

    Split out from :func:`_build_alarm_view` so that neither function has to
    hold the whole screen's worth of widgets at once; the pack order here is
    the on-screen order, and the entry sits deliberately mid-stack.
    """
    title_label = tk.Label(
        parent,
        text="WAKE UP!",
        font=config.font("display", bold=True, scale=1.5),
        fg=config.danger,
        bg=config.bg,
    )
    title_label.pack(pady=config.space("md"))

    round_label = tk.Label(
        parent,
        text=f"Round 1 / {DISMISS_ROUNDS_REQUIRED}",
        font=config.font("title", bold=True),
        fg=config.warning,
        bg=config.bg,
    )
    round_label.pack(pady=config.space("xs"))

    info_label = tk.Label(
        parent,
        text=challenge.hint,
        font=config.font("body"),
        fg=config.fg,
        bg=config.bg,
    )
    info_label.pack(pady=config.space("sm"))

    # Non-flash types use a smaller font because their display text is wider.
    # Multiples of the display token rather than raw sizes, so the challenge
    # scales with the rest of the screen (and is sized in px, not points).
    code_scale = (
        1.5 if challenge.kind in ("math", "sort", "sequence", "reverse") else 2.25
    )
    code_label = tk.Label(
        parent,
        text=challenge.display,
        font=config.font("display", bold=True, family="Courier", scale=code_scale),
        fg=config.success,
        bg=config.bg,
    )
    code_label.pack(pady=config.space("lg"))

    entry = tk.Entry(
        parent,
        font=config.font("display", family="Courier"),
        justify="center",
        width=12,
        textvariable=entry_var,
        # Tk's default focus ring is 1px BLACK, invisible on bg (#211D1B). This
        # field is already focused and Return-bound, so the ring is about
        # confirming *where* keystrokes are going -- on a screen with no other
        # window and a global grab, that is the only feedback available.
        **config.focus_kwargs(),
    )
    entry.pack(pady=config.space("sm"))
    entry.focus_set()
    entry.bind("<Return>", on_submit)

    status_label = tk.Label(
        parent,
        text="",
        font=config.font("body"),
        fg=config.danger,
        bg=config.bg,
    )
    status_label.pack(pady=config.space("sm"))

    timer_label = tk.Label(
        parent,
        text="",
        font=config.font("label"),
        fg=config.muted,
        bg=config.bg,
    )
    timer_label.pack(pady=config.space("xs"))

    return (
        _AlarmLabels(
            title=title_label,
            round_counter=round_label,
            info=info_label,
            code=code_label,
            status=status_label,
            timer=timer_label,
        ),
        entry,
    )


def _build_alarm_view(
    root: tk.Misc,
    challenge: _Challenge,
    config: LockConfig,
    *,
    on_submit: Callable[[object], None],
    entry_var: tk.StringVar,
) -> _AlarmView:
    """Build the dismiss-challenge UI and return its widgets as a view."""
    container = tk.Frame(root, bg=config.bg)
    container.place(relx=0.5, rely=0.5, anchor="center")

    # One frame around the whole challenge: the escape hatch hides it wholesale
    # and packs it straight back on cancel. Forgetting the widgets individually
    # would be irreversible -- pack_forget does not remember its options.
    challenge_frame = tk.Frame(container, bg=config.bg)
    challenge_frame.pack()

    labels, entry = _build_challenge(
        challenge_frame, challenge, config, on_submit, entry_var
    )

    # Hidden until the alarm has been up long enough; see _escape_flow.
    escape_button = tk.Button(
        challenge_frame,
        text="I can't do this right now",
        font=config.font("label"),
        bg=config.field_bg,
        fg=config.muted,
        **config.focus_kwargs(),
    )
    # Tk binds only <space> on Button on X11. The escape hatch is deliberately
    # hard to reach (hidden until earned, budgeted) but must not additionally be
    # hard to *press* once shown.
    bind_activate(escape_button)

    return _AlarmView(
        container=container,
        challenge_frame=challenge_frame,
        labels=labels,
        entry=entry,
        escape_button=escape_button,
        config=config,
    )
