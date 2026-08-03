"""Weekend wake alarm daemon with escalating beep and dismiss challenge.

Run as a systemd service on boot. Checks if today is an alarm day,
plays escalating system beeps, and presents a fullscreen dismiss
challenge (random code typing). Dismissing within the window grants a
workout-free day via HMAC-signed wake state.
"""

from __future__ import annotations

import argparse
import contextlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
import sys
import threading
import time
import tkinter as tk

from gatelock import (
    RANK_WAKE_ALARM,
    Arbiter,
    GateRoot,
    LockConfig,
    LockWindow,
    SurfaceInfo,
)

from wake_alarm._alarm_display import _restore_display, _wake_display
from wake_alarm._alarm_view import _build_alarm_view, _ViewGroup
from wake_alarm._audio import (
    _beep_loud,
    _beep_medium,
    _beep_soft,
    _max_fans,
    _play_on_all_sinks,
    _restore_fans,
    _set_max_brightness,
)
from wake_alarm._challenges import (
    _Challenge,
    _make_challenge,
)
from wake_alarm._constants import (
    ALARM_DAYS,
    DISMISS_CODE_REFRESH_SECONDS,
    DISMISS_FLASH_SECONDS,
    DISMISS_ROUNDS_REQUIRED,
    DISMISS_WINDOW_MINUTES,
    LOUD_TOGGLE_INTERVAL,
    MEDIUM_BEEP_INTERVAL,
    PHASE_MEDIUM_END,
    PHASE_SOFT_END,
    SOFT_BEEP_INTERVAL,
)
from wake_alarm._escape_flow import EscapeHatch, build_tracker
from wake_alarm._logging_setup import configure_logging
from wake_alarm._sinks import (
    _activate_all_outputs,
    _AudioState,
    _restore_audio_state,
    _warn_if_no_real_sink,
)
from wake_alarm._smart_plug import turn_off_plug, turn_on_plug
from wake_alarm._state import (
    save_wake_state,
    was_alarm_dismissed_today,
    was_workout_logged_today,
)

_logger = logging.getLogger(__name__)


def _is_alarm_day() -> bool:
    """Check if today is an alarm day."""
    return datetime.now(tz=timezone.utc).weekday() in ALARM_DAYS


@dataclass
class _AlarmProgress:
    """Mutable dismiss-challenge progress state."""

    current_challenge: _Challenge
    started_at: float = field(default_factory=time.monotonic)
    skip_earnable: bool = True
    rounds_completed: int = 0
    flash_remaining: int = 0
    flash_on: bool = False


@dataclass
class _AlarmHardware:
    """Hardware state captured at alarm start, restored when it closes."""

    fan_state: bool
    audio_restore: _AudioState | None


class WakeAlarm:
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
        # Production hard-locks as of gatelock v0.2.0. The old comment here
        # deferred it for want of "a watchdog for a clean, silent lock
        # failure" -- the recovery loop is that watchdog. Demo stays grab-free
        # so a manual test cannot trap the developer, but takes
        # overrideredirect anyway: per-output placement is impossible without
        # it, since a window manager rewrites a managed window's geometry.
        config = LockConfig(
            mode="soft" if demo_mode else "hard",
            overrideredirect=True,
            app_name="wake_alarm",
            rank=RANK_WAKE_ALARM,
        )
        # A local, not an attribute: the arbiter is published here and then
        # owned by LockWindow, which is what releases it on close.
        arbiter = Arbiter(
            "wake_alarm",
            RANK_WAKE_ALARM,
            grab=config.resolved_grab(),
            disable_vt=config.resolved_disable_vt(),
        )
        arbiter.publish()
        arbiter.acquire_holder()

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
        self._start_beep_thread()
        self._hardware = _AlarmHardware(
            fan_state=_max_fans(), audio_restore=_activate_all_outputs()
        )
        self._start_screen_flash()
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
        """Restore fans/audio/display/plug; runs on every exit path, even SIGTERM."""
        self._stop_beep.set()
        _restore_fans(active=self._hardware.fan_state)
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
        entered = self._view.entry.get().strip().upper()
        if entered != self._progress.current_challenge.answer:
            self._view.status_label.configure(text="Wrong! Try again.")
            self._view.entry.delete(0, tk.END)
            if self._progress.current_challenge.kind == "flash":
                self._view.code_label.configure(
                    text=self._progress.current_challenge.display,
                    fg=self._view.config.success,
                )
                self._start_flash_countdown()
            return
        self._progress.rounds_completed += 1
        if self._progress.rounds_completed >= DISMISS_ROUNDS_REQUIRED:
            self._dismiss_alarm(earned_skip=self._progress.skip_earnable)
            return
        self._progress.current_challenge = _make_challenge()
        self._view.code_label.configure(
            text=self._progress.current_challenge.display,
            fg=self._view.config.success,
        )
        self._view.info_label.configure(text=self._progress.current_challenge.hint)
        self._view.entry.delete(0, tk.END)
        next_round = self._progress.rounds_completed + 1
        self._view.round_label.configure(
            text=f"Round {next_round} / {DISMISS_ROUNDS_REQUIRED}",
        )
        self._view.status_label.configure(
            text=f"Round {self._progress.rounds_completed} done — keep going!",
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
            self._view.status_label.configure(
                text=f"Memorise! Hiding in {self._progress.flash_remaining}s…",
            )
            self._progress.flash_remaining -= 1
            self.root.after(1000, self._flash_tick)
        else:
            hidden = "?" * len(self._progress.current_challenge.display)
            self._view.code_label.configure(text=hidden, fg=self._view.config.muted)
            self._view.status_label.configure(text="Now type the code from memory!")

    def _dismiss_alarm(self, *, earned_skip: bool) -> None:
        """Dismiss the alarm and save state."""
        self._active = False
        self.dismissed = True
        self._stop_beep.set()
        now_iso = datetime.now(tz=timezone.utc).isoformat()
        save_wake_state(dismissed_at=now_iso, skip_workout=earned_skip)

        for container in self._view.containers:
            for widget in container.winfo_children():
                widget.destroy()

        msg = (
            "Workout skip earned! Enjoy your morning."
            if earned_skip
            else "Alarm dismissed. No workout skip."
        )
        cfg = self._view.config
        color = cfg.success if earned_skip else cfg.warning

        for container in self._view.containers:
            tk.Label(
                container,
                text=msg,
                font=cfg.font("display", bold=True),
                fg=color,
                bg=cfg.bg,
            ).pack(pady=cfg.space("lg"))

        self.root.after(3000, self._lock.close)

    def _schedule_code_refresh(self) -> None:
        """Replace the current challenge periodically.

        Ensures the user can't simply wait out a hard challenge type — a new
        random challenge is generated every DISMISS_CODE_REFRESH_SECONDS.
        """
        if not self._active:
            return
        self._progress.current_challenge = _make_challenge()
        self._view.code_label.configure(
            text=self._progress.current_challenge.display,
            fg=self._view.config.success,
        )
        self._view.info_label.configure(text=self._progress.current_challenge.hint)
        self._view.entry.delete(0, tk.END)
        if self._progress.current_challenge.kind == "flash":
            self._start_flash_countdown()
        ms = DISMISS_CODE_REFRESH_SECONDS * 1000 if not self.demo_mode else 10_000
        self.root.after(ms, self._schedule_code_refresh)

    def _schedule_skip_window_close(self) -> None:
        """Mark the workout-skip reward as expired after the allowed time."""
        ms = DISMISS_WINDOW_MINUTES * 60 * 1000 if not self.demo_mode else 30_000
        self.root.after(ms, self._on_skip_window_expired)

    def _on_skip_window_expired(self) -> None:
        """Skip window closed: keep the alarm running, deny the workout skip.

        The alarm intentionally does NOT stop here - it keeps beeping and
        flashing until the user actually types the code. Only the workout-skip
        reward expires; dismissing now silences the alarm without earning a skip.
        """
        if not self._active:
            return
        self._progress.skip_earnable = False
        self._view.info_label.configure(
            text="Skip window closed - type the code to stop the alarm",
        )
        self._view.status_label.configure(text="No workout skip today.")
        _logger.info("Skip window expired - alarm continues until dismissed.")

    def _update_timer(self) -> None:
        """Show the skip-window countdown, then a keep-going silence prompt."""
        if not self._active:
            return
        elapsed = time.monotonic() - self._progress.started_at
        window = DISMISS_WINDOW_MINUTES * 60 if not self.demo_mode else 30
        remaining = max(0, window - elapsed)
        if self._progress.skip_earnable and remaining > 0:
            minutes = int(remaining) // 60
            seconds = int(remaining) % 60
            self._view.timer_label.configure(
                text=f"Skip window: {minutes:02d}:{seconds:02d}",
            )
        else:
            self._view.timer_label.configure(
                text="No skip available - type the code to stop the alarm",
            )
        self._escape.maybe_offer(elapsed)
        self.root.after(1000, self._update_timer)

    def _on_escape_granted(self) -> None:
        """The hatch was earned: silence the alarm, grant no workout skip."""
        _logger.warning("alarm dismissed via the escape hatch, no skip earned")
        self._dismiss_alarm(earned_skip=False)

    def _start_beep_thread(self) -> None:
        """Start the background beep escalation thread."""
        thread = threading.Thread(target=self._beep_loop, daemon=True)
        thread.start()

    def _start_screen_flash(self) -> None:
        """Start flashing the screen background to attract attention."""
        self._flash_step()

    def _flash_step(self) -> None:
        """Alternate background colour every 750 ms (below seizure-risk 3 Hz)."""
        if not self._active:
            return
        cfg = self._view.config
        colour = cfg.danger if self._progress.flash_on else cfg.bg
        self.root.configure(bg=colour)
        # The per-output surfaces sit on top of the backdrop, so flashing
        # only the root would be invisible on every monitor.
        for container in self._view.containers:
            with contextlib.suppress(tk.TclError):
                container.configure(bg=colour)
                container.winfo_toplevel().configure(bg=colour)
        self._progress.flash_on = not self._progress.flash_on
        self.root.after(750, self._flash_step)

    def _beep_loop(self) -> None:
        """Escalating beep loop running in background thread."""
        while not self._stop_beep.is_set():
            elapsed_minutes = (time.monotonic() - self._progress.started_at) / 60.0

            if elapsed_minutes < PHASE_SOFT_END:
                _play_on_all_sinks(440)
                _beep_soft()
                self._stop_beep.wait(SOFT_BEEP_INTERVAL)
            elif elapsed_minutes < PHASE_MEDIUM_END:
                _play_on_all_sinks(1000)
                _beep_medium()
                self._stop_beep.wait(MEDIUM_BEEP_INTERVAL)
            else:
                freq = 800 if int(elapsed_minutes * 10) % 2 == 0 else 1200
                _play_on_all_sinks(freq)
                _beep_loud(freq)
                self._stop_beep.wait(LOUD_TOGGLE_INTERVAL)

    def run(self) -> None:
        """Start the alarm main loop, restoring hardware on every exit path."""
        self._lock.run()


def _should_run_alarm() -> bool:
    """Determine if the alarm should run right now."""
    if not _is_alarm_day():
        _logger.info("Not an alarm day. Exiting.")
        return False
    if was_alarm_dismissed_today():
        _logger.info("Alarm already dismissed today. Exiting.")
        return False
    if was_workout_logged_today():
        _logger.info("Workout already logged today. Skipping alarm.")
        return False
    return True


def _parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse CLI arguments for the alarm daemon."""
    parser = argparse.ArgumentParser(description="Wake alarm daemon.")
    parser.add_argument(
        "--production",
        action="store_true",
        help="Production mode (default; kept for systemd compatibility).",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run with a smaller window and shorter timers.",
    )
    parser.add_argument(
        "--trigger-now",
        action="store_true",
        help="Bypass the day/dismiss gate and fire the alarm immediately.",
    )
    return parser.parse_args(argv)


def main() -> None:
    """Entry point for the wake alarm daemon."""
    configure_logging()

    args = _parse_args(sys.argv[1:])

    if not args.trigger_now and not _should_run_alarm():
        return

    _logger.warning(
        "ALARM TRIGGERED at %s (demo=%s, trigger_now=%s)",
        datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
        args.demo,
        args.trigger_now,
    )
    _warn_if_no_real_sink()
    # Wake the display, then proceed immediately — no sleep hoping the monitor
    # is "up". The monitor powers on in parallel; brightness and audio don't
    # block on it, and the beep loop's per-cycle sink check picks up the HDMI
    # output the moment it enumerates.
    _wake_display()
    _set_max_brightness()
    turn_on_plug()
    alarm = WakeAlarm(demo_mode=args.demo)
    alarm.run()


if __name__ == "__main__":
    main()
