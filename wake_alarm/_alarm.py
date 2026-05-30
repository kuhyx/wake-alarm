"""Weekend wake alarm daemon with escalating beep and dismiss challenge.

Run as a systemd service on boot. Checks if today is an alarm day,
plays escalating system beeps, and presents a fullscreen dismiss
challenge (random code typing). Dismissing within the window grants a
workout-free day via HMAC-signed wake state.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import logging
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk

from python_pkg.wake_alarm._audio import (
    _activate_alarm_audio,
    _beep_loud,
    _beep_medium,
    _beep_soft,
    _max_fans,
    _play_on_extra_devices,
    _restore_alarm_audio,
    _restore_fans,
    _set_max_brightness,
    _warn_if_no_real_sink,
)
from python_pkg.wake_alarm._challenges import (
    _Challenge,
    _make_challenge,
)
from python_pkg.wake_alarm._constants import (
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
from python_pkg.wake_alarm._smart_plug import turn_off_plug, turn_on_plug
from python_pkg.wake_alarm._state import (
    save_wake_state,
    was_alarm_dismissed_today,
)

_logger = logging.getLogger(__name__)


def _is_alarm_day() -> bool:
    """Check if today is an alarm day."""
    return datetime.now(tz=timezone.utc).weekday() in ALARM_DAYS


def _wake_display() -> None:
    """Force the display on and disable screensaver during alarm."""
    xset = shutil.which("xset")
    if xset is None:
        _logger.warning("xset not on PATH; skipping display wake")
        return
    for cmd in (
        [xset, "dpms", "force", "on"],
        [xset, "s", "off"],
    ):
        subprocess.run(cmd, check=False, capture_output=True, timeout=5)


def _restore_display() -> None:
    """Re-enable screensaver after the alarm ends."""
    xset = shutil.which("xset")
    if xset is None:
        _logger.warning("xset not on PATH; skipping display restore")
        return
    subprocess.run(
        [xset, "s", "on"],
        check=False,
        capture_output=True,
        timeout=5,
    )


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
        self._beep_thread: threading.Thread | None = None
        self._alarm_start: float = time.monotonic()
        self._active = True

        self.root = tk.Tk()
        self.root.title("Wake Alarm" + (" [DEMO]" if demo_mode else ""))
        self.root.configure(bg="#1a1a1a")

        # Always hijack the full screen — demo_mode only controls timers.
        # NOTE: we intentionally do NOT call overrideredirect(True): on X11 it
        # removes WM management and the Entry widget can't receive keyboard
        # focus, so the user can't type the dismiss code. -fullscreen +
        # -topmost is enough to take over the screen while staying typeable.
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        fullscreen = True
        self.root.geometry(f"{screen_w}x{screen_h}+0+0")
        self.root.attributes("-fullscreen", fullscreen)
        self.root.attributes("-topmost", fullscreen)

        self.root.lift()
        self.root.focus_force()
        self.root.update_idletasks()

        self._current_challenge: _Challenge = _make_challenge()
        self._skip_earnable: bool = True
        self._rounds_completed: int = 0
        self._flash_remaining: int = 0
        self._build_ui()
        if self._current_challenge.kind == "flash":
            self._start_flash_countdown()
        self._schedule_code_refresh()
        self._schedule_skip_window_close()
        self._start_beep_thread()
        self._fan_state: bool = _max_fans()
        self._audio_restore: str | None = _activate_alarm_audio()
        self._flash_on: bool = False
        self._start_screen_flash()

    def _build_ui(self) -> None:
        """Build the dismiss challenge UI."""
        self._container = tk.Frame(self.root, bg="#1a1a1a")
        self._container.place(relx=0.5, rely=0.5, anchor="center")

        self._title_label = tk.Label(
            self._container,
            text="WAKE UP!",
            font=("Arial", 48, "bold"),
            fg="#ff4444",
            bg="#1a1a1a",
        )
        self._title_label.pack(pady=20)

        self._round_label = tk.Label(
            self._container,
            text=f"Round 1 / {DISMISS_ROUNDS_REQUIRED}",
            font=("Arial", 24, "bold"),
            fg="#ffaa00",
            bg="#1a1a1a",
        )
        self._round_label.pack(pady=5)

        self._info_label = tk.Label(
            self._container,
            text=self._current_challenge.hint,
            font=("Arial", 18),
            fg="white",
            bg="#1a1a1a",
        )
        self._info_label.pack(pady=10)

        # Math and sort use a smaller font because their display text is wider.
        code_font_size = 48 if self._current_challenge.kind in ("math", "sort") else 72
        self._code_label = tk.Label(
            self._container,
            text=self._current_challenge.display,
            font=("Courier", code_font_size, "bold"),
            fg="#00ff00",
            bg="#1a1a1a",
        )
        self._code_label.pack(pady=30)

        self._entry = tk.Entry(
            self._container,
            font=("Courier", 36),
            justify="center",
            width=12,
        )
        self._entry.pack(pady=10)
        self._entry.focus_set()
        self._entry.bind("<Return>", self._on_submit)

        self._status_label = tk.Label(
            self._container,
            text="",
            font=("Arial", 18),
            fg="#ff4444",
            bg="#1a1a1a",
        )
        self._status_label.pack(pady=10)

        self._timer_label = tk.Label(
            self._container,
            text="",
            font=("Arial", 14),
            fg="#aaaaaa",
            bg="#1a1a1a",
        )
        self._timer_label.pack(pady=5)
        self._update_timer()

    def _on_submit(self, _event: object = None) -> None:
        """Handle challenge submission.

        Normalises input and compares to the current challenge answer.
        Requires DISMISS_ROUNDS_REQUIRED correct entries in sequence — each
        correct round generates a new random challenge so the user must stay
        awake and re-engage each time.
        """
        entered = self._entry.get().strip().upper()
        if entered != self._current_challenge.answer:
            self._status_label.configure(text="Wrong! Try again.")
            self._entry.delete(0, tk.END)
            if self._current_challenge.kind == "flash":
                self._code_label.configure(
                    text=self._current_challenge.display,
                    fg="#00ff00",
                )
                self._start_flash_countdown()
            return
        self._rounds_completed += 1
        if self._rounds_completed >= DISMISS_ROUNDS_REQUIRED:
            self._dismiss_alarm(earned_skip=self._skip_earnable)
            return
        self._current_challenge = _make_challenge()
        self._code_label.configure(
            text=self._current_challenge.display,
            fg="#00ff00",
        )
        self._info_label.configure(text=self._current_challenge.hint)
        self._entry.delete(0, tk.END)
        next_round = self._rounds_completed + 1
        self._round_label.configure(
            text=f"Round {next_round} / {DISMISS_ROUNDS_REQUIRED}",
        )
        self._status_label.configure(
            text=f"Round {self._rounds_completed} done — keep going!",
        )
        if self._current_challenge.kind == "flash":
            self._start_flash_countdown()

    def _start_flash_countdown(self) -> None:
        """Begin the flash countdown: show code then hide it."""
        self._flash_remaining = DISMISS_FLASH_SECONDS
        self._flash_tick()

    def _flash_tick(self) -> None:
        """Decrement flash countdown; replace the displayed code with placeholders."""
        if not self._active:
            return
        if self._flash_remaining > 0:
            self._status_label.configure(
                text=f"Memorise! Hiding in {self._flash_remaining}s…",
            )
            self._flash_remaining -= 1
            self.root.after(1000, self._flash_tick)
        else:
            hidden = "?" * len(self._current_challenge.display)
            self._code_label.configure(text=hidden, fg="#555555")
            self._status_label.configure(text="Now type the code from memory!")

    def _dismiss_alarm(self, *, earned_skip: bool) -> None:
        """Dismiss the alarm and save state."""
        self._active = False
        self.dismissed = True
        self._stop_beep.set()
        now_iso = datetime.now(tz=timezone.utc).isoformat()
        save_wake_state(dismissed_at=now_iso, skip_workout=earned_skip)

        for widget in self._container.winfo_children():
            widget.destroy()

        msg = (
            "Workout skip earned! Enjoy your morning."
            if earned_skip
            else "Alarm dismissed. No workout skip."
        )
        color = "#00ff00" if earned_skip else "#ffaa00"

        tk.Label(
            self._container,
            text=msg,
            font=("Arial", 36, "bold"),
            fg=color,
            bg="#1a1a1a",
        ).pack(pady=30)

        self.root.after(3000, self._close)

    def _close(self) -> None:
        """Close the alarm window."""
        self._stop_beep.set()
        _restore_fans(active=self._fan_state)
        _restore_alarm_audio(self._audio_restore)
        _restore_display()
        turn_off_plug()
        self.root.destroy()

    def _schedule_code_refresh(self) -> None:
        """Replace the current challenge periodically.

        Ensures the user can't simply wait out a hard challenge type — a new
        random challenge is generated every DISMISS_CODE_REFRESH_SECONDS.
        """
        if not self._active:
            return
        self._current_challenge = _make_challenge()
        self._code_label.configure(
            text=self._current_challenge.display,
            fg="#00ff00",
        )
        self._info_label.configure(text=self._current_challenge.hint)
        self._entry.delete(0, tk.END)
        if self._current_challenge.kind == "flash":
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
        self._skip_earnable = False
        self._info_label.configure(
            text="Skip window closed - type the code to stop the alarm",
        )
        self._status_label.configure(text="No workout skip today.")
        _logger.info("Skip window expired - alarm continues until dismissed.")

    def _update_timer(self) -> None:
        """Show the skip-window countdown, then a keep-going silence prompt."""
        if not self._active:
            return
        elapsed = time.monotonic() - self._alarm_start
        window = DISMISS_WINDOW_MINUTES * 60 if not self.demo_mode else 30
        remaining = max(0, window - elapsed)
        if self._skip_earnable and remaining > 0:
            minutes = int(remaining) // 60
            seconds = int(remaining) % 60
            self._timer_label.configure(
                text=f"Skip window: {minutes:02d}:{seconds:02d}",
            )
        else:
            self._timer_label.configure(
                text="No skip available - type the code to stop the alarm",
            )
        self.root.after(1000, self._update_timer)

    def _start_beep_thread(self) -> None:
        """Start the background beep escalation thread."""
        self._beep_thread = threading.Thread(
            target=self._beep_loop,
            daemon=True,
        )
        self._beep_thread.start()

    def _start_screen_flash(self) -> None:
        """Start flashing the screen background to attract attention."""
        self._flash_step()

    def _flash_step(self) -> None:
        """Alternate background colour every 750 ms (below seizure-risk 3 Hz)."""
        if not self._active:
            return
        self.root.configure(bg="#ff0000" if self._flash_on else "#1a1a1a")
        self._flash_on = not self._flash_on
        self.root.after(750, self._flash_step)

    def _beep_loop(self) -> None:
        """Escalating beep loop running in background thread."""
        while not self._stop_beep.is_set():
            elapsed_minutes = (time.monotonic() - self._alarm_start) / 60.0

            if elapsed_minutes < PHASE_SOFT_END:
                _play_on_extra_devices(440)
                _beep_soft()
                self._stop_beep.wait(SOFT_BEEP_INTERVAL)
            elif elapsed_minutes < PHASE_MEDIUM_END:
                _play_on_extra_devices(1000)
                _beep_medium()
                self._stop_beep.wait(MEDIUM_BEEP_INTERVAL)
            else:
                freq = 800 if int(elapsed_minutes * 10) % 2 == 0 else 1200
                _play_on_extra_devices(freq)
                _beep_loud(freq)
                self._stop_beep.wait(LOUD_TOGGLE_INTERVAL)

    def run(self) -> None:
        """Start the alarm main loop."""
        self.root.mainloop()


def _should_run_alarm() -> bool:
    """Determine if the alarm should run right now."""
    if not _is_alarm_day():
        _logger.info("Not an alarm day. Exiting.")
        return False
    if was_alarm_dismissed_today():
        _logger.info("Alarm already dismissed today. Exiting.")
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
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

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
    _wake_display()
    _set_max_brightness()
    turn_on_plug()
    alarm = WakeAlarm(demo_mode=args.demo)
    alarm.run()


if __name__ == "__main__":
    main()
