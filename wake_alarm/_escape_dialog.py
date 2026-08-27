"""The escape-hatch dialog — the Tk form the user fills in to bail out.

Split out of ``_escape_flow.py`` for the 250-line cap. That module keeps the
policy (whether an escape may be offered at all, and the budget it spends);
this one is only the window.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import tkinter as tk
from typing import TYPE_CHECKING

from gatelock import (
    EscapeDraft,
    bind_activate,
    bind_cancel,
    escape_text_tab_trap,
)

if TYPE_CHECKING:
    from gatelock import EscapeTracker, LockConfig

    from wake_alarm._escape_flow import EscapeCallbacks

_logger = logging.getLogger(__name__)


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
            font=config.font("body"),
            fg=config.muted,
            bg=config.bg,
        )
        self._status.pack(pady=config.space("xs"))

        tk.Label(
            self.frame,
            text="Why can you not do this right now?",
            font=config.font("subtitle", bold=True),
            fg=config.fg,
            bg=config.bg,
        ).pack(pady=config.space("sm"))

        tk.Label(
            self.frame,
            text=tracker.format_recent(),
            font=config.font("caption", family="Courier"),
            fg=config.muted,
            bg=config.bg,
            justify="left",
        ).pack(pady=config.space("xs"))

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
        description.pack(pady=config.space("xs"))

        self._complaint = tk.Label(
            self.frame,
            text="",
            font=config.font("label"),
            fg=config.danger,
            bg=config.bg,
        )
        self._complaint.pack(pady=config.space("xs"))

        self._submit = tk.Button(
            self.frame,
            text="Submit",
            font=config.font("body", bold=True),
            bg=config.warning,
            fg=config.on_fill,
            command=self.submit,
            **config.focus_kwargs(),
        )
        self._submit.pack(pady=config.space("xs"))

        back = tk.Button(
            self.frame,
            text="Back to the alarm",
            font=config.font("label"),
            bg=config.field_bg,
            fg=config.fg,
            command=callbacks.on_cancel,
            **config.focus_kwargs(),
        )
        back.pack(pady=config.space("xs"))

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
            font=config.font("caption"),
            fg=config.muted,
            bg=config.bg,
        ).pack()
        entry = tk.Entry(self.frame, width=40, **config.focus_kwargs())
        entry.pack(pady=config.space("xs"))
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
