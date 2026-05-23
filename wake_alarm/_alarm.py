"""Weekend wake alarm daemon with escalating beep and dismiss challenge.

Run as a systemd service on boot. Checks if today is an alarm day,
plays escalating system beeps, and presents a fullscreen dismiss
challenge (random code typing). Dismissing within the window grants a
workout-free day via HMAC-signed wake state.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import secrets
import shutil
import string
import subprocess
import sys
import threading
import time
import tkinter as tk

from python_pkg.wake_alarm._constants import (
    ALARM_DAYS,
    DISMISS_CODE_LENGTH,
    DISMISS_CODE_REFRESH_SECONDS,
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


def _generate_code() -> str:
    """Generate a random numeric dismiss code."""
    return "".join(secrets.choice(string.digits) for _ in range(DISMISS_CODE_LENGTH))


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


def _beep_soft() -> None:
    """Play a soft system beep via terminal bell."""
    sys.stdout.write("\a")
    sys.stdout.flush()


def _speaker_test_path() -> str:
    """Resolve absolute path to speaker-test binary."""
    path = shutil.which("speaker-test")
    if path is None:
        msg = "speaker-test not found on PATH"
        raise FileNotFoundError(msg)
    return path


# Extra PipeWire sinks to always play alarm audio on (alongside the default).
# alsa_output...hdmi-stereo = GA102 → G27Q (has built-in speaker, always on).
_EXTRA_PIPEWIRE_SINKS: tuple[str, ...] = ("alsa_output.pci-0000_01_00.1.hdmi-stereo",)


def _play_on_extra_devices(frequency: int) -> None:
    """Fire-and-forget: play a sine tone on each extra PipeWire sink."""
    try:
        path = _speaker_test_path()
    except FileNotFoundError:
        _logger.warning("speaker-test missing; skipping extra-device beep")
        return
    for sink in _EXTRA_PIPEWIRE_SINKS:
        _play_tone_on_sink(path, sink, frequency)


def _play_tone_on_sink(path: str, sink: str, frequency: int) -> None:
    """Launch speaker-test for *sink*; log a warning on OSError."""
    try:
        subprocess.Popen(
            [path, "-t", "sine", "-f", str(frequency), "-l", "1"],
            env={**os.environ, "PIPEWIRE_NODE": sink},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        _logger.warning("Failed to play tone on sink %s", sink, exc_info=True)


# NCT Super I/O chip names that expose a single pwm1 fan control channel.
_NCT_CHIP_NAMES: frozenset[str] = frozenset(
    {
        "nct6775",
        "nct6779",
        "nct6791",
        "nct6792",
        "nct6793",
        "nct6795",
        "nct6796",
        "nct6797",
        "nct6798",
        "nct6799",
    }
)

# Installed by install.sh, controlled via sudoers NOPASSWD entry.
_FAN_SCRIPT: str = "/usr/local/bin/wake-alarm-fans.sh"
_SUDO_BIN: str = "/usr/bin/sudo"


def _find_fan_hwmon() -> str | None:
    """Return the hwmon directory for an NCT fan controller, or None."""
    for name_path in Path("/sys/class/hwmon").glob("hwmon*/name"):
        try:
            chip = name_path.read_text().strip()
        except OSError:
            _logger.warning("Could not read %s", name_path, exc_info=True)
            continue
        if chip in _NCT_CHIP_NAMES:
            return str(name_path.parent)
    _logger.warning(
        "No NCT super-I/O hwmon entry found; fan ramp will be skipped",
    )
    return None


def _max_fans() -> tuple[str, str, str] | None:
    """Ramp all NCT fans to 100% speed for maximum audible noise.

    Saves the current pwm1 values so they can be restored after the alarm.
    Safe: higher fan speed only lowers temperatures, never damages hardware.

    Returns:
        (hwmon_dir, old_enable, old_pwm) tuple to pass to _restore_fans(),
        or None when fan control is unavailable.
    """
    hwmon = _find_fan_hwmon()
    if hwmon is None:
        return None
    try:
        old_enable = (Path(hwmon) / "pwm1_enable").read_text().strip()
        old_pwm = (Path(hwmon) / "pwm1").read_text().strip()
    except OSError:
        _logger.warning(
            "Could not read pwm1/pwm1_enable in %s; skipping fan ramp",
            hwmon,
            exc_info=True,
        )
        return None
    try:
        result = subprocess.run(
            [_SUDO_BIN, "-n", _FAN_SCRIPT, "max"],
            check=False,
            capture_output=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        _logger.warning(
            "Fan script %s not runnable; skipping fan ramp",
            _FAN_SCRIPT,
            exc_info=True,
        )
        return None
    if result.returncode != 0:
        _logger.warning(
            "Fan script %s exited %d: %s",
            _FAN_SCRIPT,
            result.returncode,
            result.stderr.decode(errors="replace").strip(),
        )
        return None
    return (hwmon, old_enable, old_pwm)


def _restore_fans(state: tuple[str, str, str] | None) -> None:
    """Restore fan speed to the values saved by _max_fans()."""
    if state is None:
        return
    _hwmon, old_enable, old_pwm = state
    try:
        subprocess.run(
            [_SUDO_BIN, "-n", _FAN_SCRIPT, "restore", old_enable, old_pwm],
            check=False,
            capture_output=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        _logger.warning(
            "Failed to restore fan state via %s",
            _FAN_SCRIPT,
            exc_info=True,
        )


def _set_max_brightness() -> None:
    """Set all connected monitors to maximum brightness via xrandr."""
    xrandr = shutil.which("xrandr")
    if xrandr is None:
        _logger.warning("xrandr not on PATH; skipping max-brightness")
        return
    try:
        result = subprocess.run(
            [xrandr, "--query"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        _logger.warning("xrandr --query failed; skipping max-brightness", exc_info=True)
        return
    for line in result.stdout.splitlines():
        if " connected" in line:
            output = line.split()[0]
            try:
                subprocess.run(
                    [xrandr, "--output", output, "--brightness", "1.0"],
                    check=False,
                    capture_output=True,
                    timeout=5,
                )
            except (OSError, subprocess.TimeoutExpired):
                _logger.warning(
                    "Failed to set brightness on %s",
                    output,
                    exc_info=True,
                )


def _beep_medium(frequency: int = 1000) -> None:
    """Play a medium beep via speaker-test (sine wave, short)."""
    try:
        subprocess.run(
            [
                _speaker_test_path(),
                "-t",
                "sine",
                "-f",
                str(frequency),
                "-l",
                "1",
            ],
            capture_output=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        _logger.warning(
            "_beep_medium subprocess failed; falling back to soft beep",
            exc_info=True,
        )
        _beep_soft()


def _beep_loud(frequency: int = 1000) -> None:
    """Play a loud sine tone via speaker-test."""
    try:
        subprocess.run(
            [
                _speaker_test_path(),
                "-t",
                "sine",
                "-f",
                str(frequency),
                "-l",
                "1",
            ],
            capture_output=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        _logger.warning(
            "_beep_loud subprocess failed; falling back to soft beep",
            exc_info=True,
        )
        _beep_soft()


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

        if demo_mode:
            self.root.geometry("800x600")
        else:
            screen_w = self.root.winfo_screenwidth()
            screen_h = self.root.winfo_screenheight()
            fullscreen = True
            self.root.overrideredirect(boolean=fullscreen)
            self.root.geometry(f"{screen_w}x{screen_h}+0+0")
            self.root.attributes("-fullscreen", fullscreen)
            self.root.attributes("-topmost", fullscreen)

        self._current_code = _generate_code()
        self._build_ui()
        self._schedule_code_refresh()
        self._schedule_dismiss_window_close()
        self._start_beep_thread()
        self._fan_state: tuple[str, str, str] | None = _max_fans()
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

        self._info_label = tk.Label(
            self._container,
            text="Type the code below to earn a workout-free day",
            font=("Arial", 18),
            fg="white",
            bg="#1a1a1a",
        )
        self._info_label.pack(pady=10)

        self._code_label = tk.Label(
            self._container,
            text=self._current_code,
            font=("Courier", 72, "bold"),
            fg="#00ff00",
            bg="#1a1a1a",
        )
        self._code_label.pack(pady=30)

        self._entry = tk.Entry(
            self._container,
            font=("Courier", 36),
            justify="center",
            width=DISMISS_CODE_LENGTH + 2,
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
        """Handle code submission."""
        entered = self._entry.get().strip()
        if entered == self._current_code:
            self._dismiss_alarm(earned_skip=True)
        else:
            self._status_label.configure(text="Wrong code! Try again.")
            self._entry.delete(0, tk.END)

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
        _restore_fans(self._fan_state)
        _restore_display()
        turn_off_plug()
        self.root.destroy()

    def _schedule_code_refresh(self) -> None:
        """Refresh the dismiss code periodically."""
        if not self._active:
            return
        self._current_code = _generate_code()
        self._code_label.configure(text=self._current_code)
        self._entry.delete(0, tk.END)
        ms = DISMISS_CODE_REFRESH_SECONDS * 1000 if not self.demo_mode else 10_000
        self.root.after(ms, self._schedule_code_refresh)

    def _schedule_dismiss_window_close(self) -> None:
        """Close dismiss window after the allowed time."""
        ms = DISMISS_WINDOW_MINUTES * 60 * 1000 if not self.demo_mode else 30_000
        self.root.after(ms, self._on_dismiss_window_expired)

    def _on_dismiss_window_expired(self) -> None:
        """Called when the dismiss window expires without valid dismissal."""
        if not self._active:
            return
        self._active = False
        self._stop_beep.set()
        save_wake_state(dismissed_at=None, skip_workout=False)
        _logger.info("Dismiss window expired — no workout skip.")

        for widget in self._container.winfo_children():
            widget.destroy()

        tk.Label(
            self._container,
            text="Too late! No workout skip today.",
            font=("Arial", 36, "bold"),
            fg="#ff4444",
            bg="#1a1a1a",
        ).pack(pady=30)

        self.root.after(5000, self._close_and_schedule_fallback)

    def _close_and_schedule_fallback(self) -> None:
        """Close the window and schedule the 1 PM fallback alarm."""
        _restore_fans(self._fan_state)
        _restore_display()
        turn_off_plug()
        self.root.destroy()

    def _update_timer(self) -> None:
        """Update the remaining time display."""
        if not self._active:
            return
        elapsed = time.monotonic() - self._alarm_start
        window = DISMISS_WINDOW_MINUTES * 60 if not self.demo_mode else 30
        remaining = max(0, window - elapsed)
        minutes = int(remaining) // 60
        seconds = int(remaining) % 60
        self._timer_label.configure(
            text=f"Time remaining: {minutes:02d}:{seconds:02d}",
        )
        if remaining > 0:
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


def main() -> None:
    """Entry point for the wake alarm daemon."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    if not _should_run_alarm():
        return

    demo_mode = "--demo" in sys.argv
    _wake_display()
    _set_max_brightness()
    turn_on_plug()
    alarm = WakeAlarm(demo_mode=demo_mode)
    alarm.run()


if __name__ == "__main__":
    main()
