"""Wake alarm: escalating beeps behind a fullscreen dismiss challenge.

Started by ``morning-routine.service``, never directly (AGENTS.md). Gate:
``_gating``. Sound: ``_beep_loop``. Timers: ``_alarm_timers``.
"""

from __future__ import annotations

import contextlib
from datetime import datetime, timezone
import logging
import sys
import threading
import tkinter as tk

from gatelock import (
    GateRoot,
    LockWindow,
    SurfaceInfo,
)

from wake_alarm._alarm_display import _restore_display
from wake_alarm._alarm_state import _AlarmHardware, _AlarmProgress
from wake_alarm._alarm_timers import AlarmTimersMixin
from wake_alarm._alarm_view import _build_alarm_view, _ViewGroup
from wake_alarm._beep_loop import start_beep_thread
from wake_alarm._challenges import (
    _make_challenge,
)
from wake_alarm._constants import (
    DISMISS_FLASH_SECONDS,
    DISMISS_ROUNDS_REQUIRED,
)
from wake_alarm._escape_flow import EscapeHatch, build_tracker
from wake_alarm._gating import parse_args, should_run_alarm
from wake_alarm._lock_setup import build_config, claim_arbiter
from wake_alarm._logging_setup import configure_logging
from wake_alarm._rounds import (
    BANNER_LINGER_MS,
    FLASH_PERIOD_MS,
    apply_flash_colour,
    hide_flash_code,
    normalise,
    show_challenge,
    show_dismissal,
    show_flash_countdown,
    show_round_progress,
    show_wrong_answer,
)
from wake_alarm._sinks import (
    _activate_all_outputs,
    _restore_audio_state,
)
from wake_alarm._smart_plug import turn_off_plug
from wake_alarm._startup import prepare_hardware
from wake_alarm._state import (
    save_wake_state,
)

_logger = logging.getLogger(__name__)


class WakeAlarm(AlarmTimersMixin):
    """Fullscreen wake alarm with escalating beep and dismiss challenge."""

    def __init__(self, *, demo_mode: bool = False) -> None:
        """Initialize the wake alarm.

        Args:
            demo_mode: If True, use a smaller window and shorter timers.
        """
        self.demo_mode = demo_mode
        self.dismissed = False
        self._stop_beep = threading.Event()
        self._active = True

        self.root = GateRoot()
        self.root.on_callback_error = self.on_callback_error
        self.root.title("Wake Alarm" + (" [DEMO]" if demo_mode else ""))
        config = build_config(demo_mode=demo_mode)
        # A local, not an attribute: the arbiter is published here and then
        # owned by LockWindow, which is what releases it on close.
        arbiter = claim_arbiter(config)

        # Built before setup(): setup() calls build_surface for every live
        # output, and those need the challenge and the shared entry variable.
        self._progress = _AlarmProgress(current_challenge=_make_challenge())
        self._view = _ViewGroup(config, tk.StringVar(master=self.root))
        self._escape = EscapeHatch(build_tracker(), self._view, self._on_escape_granted)

        self._lock = LockWindow(self.root, config, hooks=self, arbiter=arbiter)
        self._lock.setup()
        self._update_timer()
        if self._progress.current_challenge.kind == "flash":
            self._start_flash_countdown()
        self._schedule_code_refresh()
        self._schedule_skip_window_close()
        start_beep_thread(self._stop_beep, self._progress.started_at)
        self._hardware = _AlarmHardware(audio_restore=_activate_all_outputs())
        self._flash_step()
        self._lock.grab_input()

    def build_surface(self, parent: tk.Misc, surface: SurfaceInfo) -> None:
        """Paint the full challenge on one monitor.

        Called once per live output, and again whenever an output comes
        back. Every copy shares one entry variable and one submit handler,
        so answering on any monitor dismisses the alarm on all of them.
        """
        view = _build_alarm_view(
            parent,
            self._progress.current_challenge,
            self._view.config,
            on_submit=self._on_submit,
            entry_var=self._view.entry_var,
        )
        view.output_name = surface.output_name
        view.escape_button.configure(command=self._escape.open)
        self._view.add(view)

    def teardown_surface(self, surface: SurfaceInfo) -> None:
        """Forget the view for an output that went dark."""
        self._view.discard(surface.output_name)

    def on_focus_ready(self, surface: SurfaceInfo | None) -> None:
        """Put keyboard focus on the dismiss-code entry once mapped.

        ``surface`` is None when no output is live -- the alarm is armed
        and audible with nothing to show, so there is nothing to focus.
        """
        if surface is None:
            return
        with contextlib.suppress(tk.TclError):
            self._view.entry.focus_force()

    def on_callback_error(self) -> None:
        """Surface an unexpected callback error without dropping the alarm."""
        with contextlib.suppress(tk.TclError):
            self._view.status_label.configure(
                text="Something went wrong — try again.",
            )
            self._view.entry.focus_force()

    def on_close(self) -> None:
        """Restore audio/display/plug; runs on every exit path, even SIGTERM."""
        self._stop_beep.set()
        _restore_audio_state(self._hardware.audio_restore)
        _restore_display()
        turn_off_plug()

    def _on_submit(self, _event: object = None) -> None:
        """Handle challenge submission.

        Normalises input and compares to the current challenge answer.
        Requires DISMISS_ROUNDS_REQUIRED correct entries in sequence — each
        correct round generates a new random challenge so the user must stay
        awake and re-engage each time.
        """
        entered = normalise(self._view.entry.get())
        if entered != self._progress.current_challenge.answer:
            show_wrong_answer(self._view, self._progress.current_challenge)
            if self._progress.current_challenge.kind == "flash":
                self._start_flash_countdown()
            return
        self._progress.rounds_completed += 1
        if self._progress.rounds_completed >= DISMISS_ROUNDS_REQUIRED:
            self._dismiss_alarm(earned_skip=self._progress.skip_earnable)
            return
        self._progress.current_challenge = _make_challenge()
        show_challenge(self._view, self._progress.current_challenge)
        show_round_progress(
            self._view,
            completed=self._progress.rounds_completed,
            required=DISMISS_ROUNDS_REQUIRED,
        )
        if self._progress.current_challenge.kind == "flash":
            self._start_flash_countdown()

    def _start_flash_countdown(self) -> None:
        """Begin the flash countdown: show code then hide it."""
        self._progress.flash_remaining = DISMISS_FLASH_SECONDS
        self._flash_tick()

    def _flash_tick(self) -> None:
        """Decrement flash countdown; replace the displayed code with placeholders."""
        if not self._active:
            return
        if self._progress.flash_remaining > 0:
            show_flash_countdown(self._view, self._progress.flash_remaining)
            self._progress.flash_remaining -= 1
            self.root.after(1000, self._flash_tick)
        else:
            hide_flash_code(self._view, self._progress.current_challenge)

    def _dismiss_alarm(self, *, earned_skip: bool) -> None:
        """Dismiss the alarm and save state."""
        self._active = False
        self.dismissed = True
        self._stop_beep.set()
        now_iso = datetime.now(tz=timezone.utc).isoformat()
        save_wake_state(dismissed_at=now_iso, skip_workout=earned_skip)
        show_dismissal(
            self._view.containers,
            self._view.config,
            earned_skip=earned_skip,
        )
        self.root.after(BANNER_LINGER_MS, self._lock.close)

    def _on_escape_granted(self) -> None:
        """The hatch was earned: silence the alarm, grant no workout skip."""
        _logger.warning("alarm dismissed via the escape hatch, no skip earned")
        self._dismiss_alarm(earned_skip=False)

    def _flash_step(self) -> None:
        """Alternate the background colour to keep the screen attention-grabbing."""
        if not self._active:
            return
        cfg = self._view.config
        colour = cfg.danger if self._progress.flash_on else cfg.bg
        apply_flash_colour(self.root, self._view.containers, colour)
        self._progress.flash_on = not self._progress.flash_on
        self.root.after(FLASH_PERIOD_MS, self._flash_step)

    def run(self) -> None:
        """Start the alarm main loop, restoring hardware on every exit path."""
        self._lock.run()


def main() -> None:
    """Entry point for the wake alarm daemon."""
    configure_logging()

    args = parse_args(sys.argv[1:])

    if not args.trigger_now and not should_run_alarm():
        return

    _logger.warning(
        "ALARM TRIGGERED at %s (demo=%s, trigger_now=%s)",
        datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
        args.demo,
        args.trigger_now,
    )
    prepare_hardware()
    alarm = WakeAlarm(demo_mode=args.demo)
    alarm.run()


if __name__ == "__main__":
    main()
