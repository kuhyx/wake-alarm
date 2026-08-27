"""Timers that run for the whole life of the alarm.

Split out of ``_alarm.py`` for the 250-line cap, as a mixin rather than free
functions because every one of these reschedules itself through ``root.after``
and needs the alarm's own view and progress state.

Note ``_on_skip_window_expired`` deliberately does **not** stop the alarm: only
the workout-skip reward expires. The alarm keeps sounding until the challenge
is actually typed.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from wake_alarm._challenges import _make_challenge
from wake_alarm._rounds import (
    NO_SKIP_STATUS,
    WINDOW_CLOSED_INFO,
    countdown_text,
    refresh_interval_ms,
    remaining_seconds,
    show_challenge,
    skip_window_ms,
    skip_window_seconds,
)

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable
    import tkinter as tk

    from wake_alarm._alarm_state import _AlarmProgress
    from wake_alarm._alarm_view import _ViewGroup
    from wake_alarm._escape_flow import EscapeHatch

_logger = logging.getLogger(__name__)


class AlarmTimersMixin:
    """Self-rescheduling timers for the challenge refresh and skip window."""

    # Provided by WakeAlarm; declared so type checking sees them.
    demo_mode: bool
    root: tk.Misc
    _active: bool
    _progress: _AlarmProgress
    _view: _ViewGroup
    _escape: EscapeHatch

    # Supplied by AlarmFlashMixin, which WakeAlarm also inherits. Declared
    # rather than stubbed: an abstract stub here would win the MRO (this mixin
    # is listed first) and shadow the real implementation.
    _start_flash_countdown: Callable[[], None]

    def _schedule_code_refresh(self) -> None:
        """Replace the current challenge periodically.

        Ensures the user can't simply wait out a hard challenge type — a new
        random challenge is generated every DISMISS_CODE_REFRESH_SECONDS.
        """
        if not self._active:
            return
        self._progress.current_challenge = _make_challenge()
        show_challenge(self._view, self._progress.current_challenge)
        if self._progress.current_challenge.kind == "flash":
            self._start_flash_countdown()
        self.root.after(
            refresh_interval_ms(demo_mode=self.demo_mode),
            self._schedule_code_refresh,
        )

    def _schedule_skip_window_close(self) -> None:
        """Mark the workout-skip reward as expired after the allowed time."""
        self.root.after(
            skip_window_ms(demo_mode=self.demo_mode),
            self._on_skip_window_expired,
        )

    def _on_skip_window_expired(self) -> None:
        """Skip window closed: keep the alarm running, deny the workout skip.

        The alarm intentionally does NOT stop here - it keeps beeping and
        flashing until the user actually types the code. Only the workout-skip
        reward expires; dismissing now silences the alarm without earning a skip.
        """
        if not self._active:
            return
        self._progress.skip_earnable = False
        self._view.info_label.configure(text=WINDOW_CLOSED_INFO)
        self._view.status_label.configure(text=NO_SKIP_STATUS)
        _logger.info("Skip window expired - alarm continues until dismissed.")

    def _update_timer(self) -> None:
        """Show the skip-window countdown, then a keep-going silence prompt."""
        if not self._active:
            return
        elapsed = time.monotonic() - self._progress.started_at
        remaining = remaining_seconds(
            elapsed,
            skip_window_seconds(demo_mode=self.demo_mode),
        )
        self._view.timer_label.configure(
            text=countdown_text(
                remaining,
                earnable=self._progress.skip_earnable,
            ),
        )
        self._escape.maybe_offer(elapsed)
        self.root.after(1000, self._update_timer)
