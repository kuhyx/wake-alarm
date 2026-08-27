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
    EscapePolicy,
    EscapeTracker,
)

from wake_alarm._constants import ESCAPE_HISTORY_FILE, ESCAPE_OFFER_AFTER_SECONDS
from wake_alarm._escape_dialog import EscapeDialog, _FormFields

# Imported under their original names: the suite patches
# `wake_alarm._escape_flow.EscapeDialog`, and a moved symbol makes patch()
# stop intercepting silently. __all__ stops ruff deleting them as unused.
__all__ = ["EscapeDialog", "EscapeHatch", "_FormFields"]

if TYPE_CHECKING:
    from collections.abc import Callable

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
                button.pack(pady=self._views.config.space("sm"))

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
