"""The alarm's sanctioned way out when the challenge genuinely isn't happening.

Until now the alarm had exactly one exit: four correct challenge rounds against
a 30-second refresh. That is a lot to ask of someone who has just woken up, and
it is *nothing* to fall back on if the alarm misfires at the wrong hour. Every
other locker here has a bounded escape -- screen-locker's sick mode,
diet-guard's log-a-meal -- so the alarm now has the same, built on the shared
:mod:`gatelock._escape` core rather than a private copy.

The shape, deliberately identical to sick mode:

* the button only appears after the alarm has been up a while, so it is never
  the *easy* first move;
* it disappears entirely once any rolling budget is spent;
* it costs a written justification, with the last ten shown back to you;
* it costs a wait that doubles with each recent use;
* every entry is HMAC-signed, so editing the history is detectable.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
import logging
import tkinter as tk
from typing import TYPE_CHECKING

from gatelock import (
    EscapeDraft,
    EscapePolicy,
    EscapeTracker,
    bind_activate,
    bind_cancel,
    escape_text_tab_trap,
)

from wake_alarm._constants import ESCAPE_HISTORY_FILE, ESCAPE_OFFER_AFTER_SECONDS

if TYPE_CHECKING:
    from collections.abc import Callable

    from gatelock import LockConfig

    from wake_alarm._alarm_view import _ViewGroup


_logger = logging.getLogger(__name__)

ALARM_ESCAPE_POLICY = EscapePolicy(
    name="cant-wake",
    label="Can't-wake",
)
"""Budgets left at the shared defaults, so this is exactly as hard as sick mode."""


def build_tracker() -> EscapeTracker:
    """Build the alarm's escape tracker over its own history file."""
    tracker = EscapeTracker(ALARM_ESCAPE_POLICY, ESCAPE_HISTORY_FILE)
    tracker.load()
    return tracker


def is_offerable(tracker: EscapeTracker, elapsed_seconds: float) -> bool:
    """Whether the hatch should be shown at all.

    Two independent gates: the alarm must have been up long enough that this
    is not the first thing you reach for, and the budget must not be spent.
    """
    if elapsed_seconds < ESCAPE_OFFER_AFTER_SECONDS:
        return False
    return not tracker.is_budget_exhausted()


@dataclass(frozen=True)
class EscapeCallbacks:
    """Who to tell how the form ended."""

    on_granted: Callable[[], None]
    on_cancel: Callable[[], None]


@dataclass
class _FormFields:
    """The four inputs the justification is read back out of."""

    reason: tk.Entry
    onset: tk.Entry
    severity: tk.Entry
    description: tk.Text


class EscapeDialog:
    """The justification form and its escalating wait."""

    def __init__(
        self,
        parent: tk.Misc,
        config: LockConfig,
        tracker: EscapeTracker,
        callbacks: EscapeCallbacks,
    ) -> None:
        """Build the form inside ``parent``."""
        self._tracker = tracker
        self._callbacks = callbacks
        self._remaining = 0

        self.frame = tk.Frame(parent, bg=config.bg)
        self._status = tk.Label(
            self.frame,
            text=tracker.budget_summary(),
            font=(config.font_family, 16),
            fg=config.muted,
            bg=config.bg,
        )
        self._status.pack(pady=6)

        tk.Label(
            self.frame,
            text="Why can you not do this right now?",
            font=(config.font_family, 22, "bold"),
            fg=config.fg,
            bg=config.bg,
        ).pack(pady=8)

        tk.Label(
            self.frame,
            text=tracker.format_recent(),
            font=("Courier", 11),
            fg=config.muted,
            bg=config.bg,
            justify="left",
        ).pack(pady=6)

        description = tk.Text(
            self.frame,
            height=4,
            width=60,
            wrap="word",
            bg=config.field_bg,
            fg=config.fg,
            insertbackground=config.fg,
            **config.focus_kwargs(),
        )
        # Tk traps Tab inside a Text (inserts a literal tab and refocuses the
        # widget) and binds Shift-Tab to nothing, so the only exits are the
        # undocumented Ctrl+Tab / Ctrl+Shift+Tab. Unlike diet_guard's equivalent
        # box, nothing here bound Return either -- so a keyboard-only user who
        # tabbed into this justification field at 6am could not reach Submit,
        # inside an alarm whose whole point is that it resists dismissal.
        escape_text_tab_trap(description)
        self._fields = _FormFields(
            reason=self._field("What is wrong", config),
            onset=self._field("When did it start", config),
            severity=self._field("Severity 1-10", config),
            description=description,
        )
        description.pack(pady=6)

        self._complaint = tk.Label(
            self.frame,
            text="",
            font=(config.font_family, 14),
            fg=config.danger,
            bg=config.bg,
        )
        self._complaint.pack(pady=4)

        self._submit = tk.Button(
            self.frame,
            text="Submit",
            font=(config.font_family, 16, "bold"),
            bg=config.warning,
            fg=config.on_fill,
            command=self.submit,
            **config.focus_kwargs(),
        )
        self._submit.pack(pady=6)

        back = tk.Button(
            self.frame,
            text="Back to the alarm",
            font=(config.font_family, 14),
            bg=config.field_bg,
            fg=config.fg,
            command=callbacks.on_cancel,
            **config.focus_kwargs(),
        )
        back.pack(pady=4)

        # Tk binds only <space> on Button on X11, never <Return>, so Enter --
        # the key a user reaches for to submit a form -- did nothing at all.
        for button in (self._submit, back):
            bind_activate(button)
        # Escape returns to the alarm. This cancels the *escape-hatch form*, not
        # the alarm: the alarm still has to be dismissed by solving a challenge
        # or by spending the budgeted hatch. Making the sanctioned way back
        # keyboard-reachable does not weaken that gating.
        bind_cancel(self.frame, callbacks.on_cancel)

    def _field(self, label: str, config: LockConfig) -> tk.Entry:
        """Add a labelled single-line field and return its entry."""
        tk.Label(
            self.frame,
            text=label,
            font=(config.font_family, 13),
            fg=config.muted,
            bg=config.bg,
        ).pack()
        entry = tk.Entry(self.frame, width=40, **config.focus_kwargs())
        entry.pack(pady=2)
        return entry

    def _draft(self) -> EscapeDraft:
        """Read the form into a draft."""
        try:
            severity = int(self._fields.severity.get().strip() or "0")
        except ValueError:
            severity = 0
        return EscapeDraft(
            reason=self._fields.reason.get(),
            onset=self._fields.onset.get(),
            severity=severity,
            description=self._fields.description.get("1.0", "end-1c"),
        )

    def submit(self) -> None:
        """Validate, then start the escalating wait."""
        draft = self._draft()
        complaint = self._tracker.validate(draft)
        if complaint is not None:
            self._complaint.configure(text=complaint)
            return
        if self._tracker.is_budget_exhausted():
            # Re-checked at submit time: the budget could have been spent by
            # another surface, or the day could have rolled over mid-form.
            self._complaint.configure(text="No budget left. Solve the challenge.")
            return
        self._tracker.record(draft)
        self._remaining = self._tracker.compute_lockout_seconds()
        self._submit.configure(state="disabled")
        self._tick()

    def _tick(self) -> None:
        """Count the wait down, then grant."""
        if self._remaining <= 0:
            _logger.warning(
                "alarm escape hatch used -- %s", self._tracker.budget_summary()
            )
            self._callbacks.on_granted()
            return
        self._complaint.configure(text=f"Wait {self._remaining}s...")
        self._remaining -= 1
        self.frame.after(1000, self._tick)


class EscapeHatch:
    """The alarm's way out, from the hidden button to putting the screen back.

    The alarm delegates the whole flow here so that opening and closing the
    form stay symmetric: every ``open`` that hides a challenge and builds a
    dialog has a ``close`` that destroys the dialog and packs the challenge
    back. Splitting those halves across two objects is what previously left
    "Back to the alarm" showing a blank screen.
    """

    def __init__(
        self,
        tracker: EscapeTracker,
        views: _ViewGroup,
        on_granted: Callable[[], None],
    ) -> None:
        """Bind the hatch to the surfaces it swaps and the alarm it releases."""
        self._tracker = tracker
        self._views = views
        self._on_granted = on_granted
        self._dialogs: list[EscapeDialog] = []
        self.is_open = False

    def maybe_offer(self, elapsed_seconds: float) -> None:
        """Reveal the button on every monitor once it is earned, and only then."""
        if self.is_open:
            return
        if not is_offerable(self._tracker, elapsed_seconds):
            return
        for button in self._views.escape_buttons:
            with contextlib.suppress(tk.TclError):
                button.pack(pady=8)

    def open(self) -> None:
        """Swap every surface over to the justification form."""
        self.is_open = True
        callbacks = EscapeCallbacks(
            on_granted=self._on_granted,
            on_cancel=self.close,
        )
        for view in self._views.surfaces:
            with contextlib.suppress(tk.TclError):
                view.challenge_frame.pack_forget()
                dialog = EscapeDialog(
                    view.container,
                    self._views.config,
                    self._tracker,
                    callbacks,
                )
                dialog.frame.pack()
                self._dialogs.append(dialog)

    def close(self) -> None:
        """Back out of the form and put the challenge back on every monitor."""
        for dialog in self._dialogs:
            with contextlib.suppress(tk.TclError):
                dialog.frame.destroy()
        self._dialogs.clear()
        for view in self._views.surfaces:
            with contextlib.suppress(tk.TclError):
                view.challenge_frame.pack()
        self.is_open = False
