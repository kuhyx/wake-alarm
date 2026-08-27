"""Screen-flash timers: the flash challenge countdown and the colour pulse.

Split out of ``_alarm.py`` for the 250-line cap, as a mixin rather than free
functions because each of these reschedules itself through ``root.after`` and
needs the alarm's own view and progress state -- the same shape as
``AlarmTimersMixin``.

Two independent flashes live here and must not be confused:

* the **challenge** countdown (:meth:`_start_flash_countdown`) shows a code for
  ``DISMISS_FLASH_SECONDS`` and then hides it, so the user has to memorise it;
* the **background** pulse (:meth:`_flash_step`) alternates the window colour
  forever, so the screen keeps demanding attention.

Both stop the moment ``_active`` goes false, which is what keeps a dismissed
alarm from repainting a window that is on its way out.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from wake_alarm._constants import DISMISS_FLASH_SECONDS
from wake_alarm._rounds import (
    FLASH_PERIOD_MS,
    apply_flash_colour,
    hide_flash_code,
    show_flash_countdown,
)

if TYPE_CHECKING:  # pragma: no cover
    import tkinter as tk

    from wake_alarm._alarm_state import _AlarmProgress
    from wake_alarm._alarm_view import _ViewGroup


class AlarmFlashMixin:
    """Self-rescheduling flash timers for the code countdown and background."""

    # Provided by WakeAlarm; declared so type checking sees them.
    root: tk.Misc
    _active: bool
    _progress: _AlarmProgress
    _view: _ViewGroup

    def _start_flash_countdown(self) -> None:
        """Begin the flash countdown: show the code, then hide it."""
        self._progress.flash_remaining = DISMISS_FLASH_SECONDS
        self._flash_tick()

    def _flash_tick(self) -> None:
        """Count the code down, then replace it with placeholders."""
        if not self._active:
            return
        if self._progress.flash_remaining > 0:
            show_flash_countdown(self._view, self._progress.flash_remaining)
            self._progress.flash_remaining -= 1
            self.root.after(1000, self._flash_tick)
        else:
            hide_flash_code(self._view, self._progress.current_challenge)

    def _flash_step(self) -> None:
        """Alternate the background colour to keep the screen attention-grabbing."""
        if not self._active:
            return
        cfg = self._view.config
        colour = cfg.danger if self._progress.flash_on else cfg.bg
        apply_flash_colour(self.root, self._view.containers, colour)
        self._progress.flash_on = not self._progress.flash_on
        self.root.after(FLASH_PERIOD_MS, self._flash_step)
