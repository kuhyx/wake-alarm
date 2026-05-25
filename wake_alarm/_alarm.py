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
import math
import os
from pathlib import Path
import secrets
import shutil
import string
import struct
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
import wave

from python_pkg.wake_alarm._constants import (
    ALARM_AUDIO_CARD,
    ALARM_AUDIO_PROFILE,
    ALARM_AUDIO_SINK,
    ALARM_AUDIO_SINK_POLL_SECONDS,
    ALARM_AUDIO_SINK_WAIT_SECONDS,
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


_TONE_CACHE: dict[int, Path] = {}
_TONE_TIMEOUT_SECONDS: float = 6.0
_TONE_DURATION_SECONDS: float = 1.5
_TONE_FRAMERATE: int = 48000
_TONE_AMPLITUDE: int = 32760  # near s16 max for the loudest sine we can emit

# Number of back-to-back PC-speaker beeps per _play_tone call.
# pcspkr volume is hardware-fixed, so we lean on repetition + duration to be
# loud enough to actually wake the user.
_PCSPKR_REPEATS: int = 3
_PCSPKR_GAP_SECONDS: float = 0.12

# Motherboard PC speaker exposed by the pcspkr kernel module.
# Writing EV_SND/SND_TONE input_event structs makes it beep — bypasses
# PipeWire/ALSA entirely, so it stays audible even when no real sink exists.
_PCSPKR_DEVICE: str = "/dev/input/by-path/platform-pcspkr-event-spkr"
_PCSPKR_EV_SND: int = 0x12
_PCSPKR_SND_TONE: int = 0x02
# struct input_event: timeval (long sec, long usec), u16 type, u16 code, s32 val
_PCSPKR_EVENT_FMT: str = "llHHi"


def _beep_pcspkr(frequency: int, duration_seconds: float) -> None:
    """Beep the motherboard PC speaker via evdev (audible without any sink).

    Silently no-ops when the device is missing or unwritable so the call is
    always safe from the alarm hot path.
    """
    try:
        # buffering=0 so the write hits the device immediately.
        with Path(_PCSPKR_DEVICE).open("wb", buffering=0) as dev:
            dev.write(
                struct.pack(
                    _PCSPKR_EVENT_FMT,
                    0,
                    0,
                    _PCSPKR_EV_SND,
                    _PCSPKR_SND_TONE,
                    int(frequency),
                ),
            )
            time.sleep(duration_seconds)
            dev.write(
                struct.pack(
                    _PCSPKR_EVENT_FMT,
                    0,
                    0,
                    _PCSPKR_EV_SND,
                    _PCSPKR_SND_TONE,
                    0,
                ),
            )
    except OSError:
        _logger.warning(
            "PC speaker beep at %d Hz failed (device %s)",
            frequency,
            _PCSPKR_DEVICE,
            exc_info=True,
        )


def _ensure_tone_wav(frequency: int) -> Path:
    """Generate (and cache) a mono 48 kHz sine WAV at *frequency* Hz."""
    cached = _TONE_CACHE.get(frequency)
    if cached is not None and cached.exists():
        return cached
    path = Path(tempfile.gettempdir()) / f"wake_alarm_tone_{frequency}.wav"
    n_frames = int(_TONE_FRAMERATE * _TONE_DURATION_SECONDS)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(_TONE_FRAMERATE)
        frames = bytearray()
        for i in range(n_frames):
            sample = int(
                _TONE_AMPLITUDE
                * math.sin(2 * math.pi * frequency * i / _TONE_FRAMERATE),
            )
            frames.extend(struct.pack("<h", sample))
        wav.writeframesraw(bytes(frames))
    _TONE_CACHE[frequency] = path
    return path


def _try_player(binary: str, wav: Path) -> bool:
    """Run *binary* on *wav* with a generous timeout. Return True on success."""
    path = shutil.which(binary)
    if path is None:
        return False
    try:
        result = subprocess.run(
            [path, str(wav)],
            capture_output=True,
            timeout=_TONE_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        _logger.warning("%s failed playing %s", binary, wav.name, exc_info=True)
        return False
    if result.returncode != 0:
        _logger.warning(
            "%s exited %d for %s: %s",
            binary,
            result.returncode,
            wav.name,
            result.stderr.decode(errors="replace").strip()[:200],
        )
        return False
    return True


def _play_tone(frequency: int) -> None:
    """Play a sine tone via paplay/aplay/speaker-test, fall back to soft beep.

    Always also beeps the motherboard PC speaker (multiple times) so the
    alarm stays loud and audible even when PipeWire only has the auto_null
    sink.
    """
    for i in range(_PCSPKR_REPEATS):
        _beep_pcspkr(frequency, _TONE_DURATION_SECONDS)
        if i < _PCSPKR_REPEATS - 1:
            time.sleep(_PCSPKR_GAP_SECONDS)
    try:
        wav = _ensure_tone_wav(frequency)
    except OSError:
        _logger.warning(
            "Could not generate tone WAV at %d Hz; using soft beep",
            frequency,
            exc_info=True,
        )
        _beep_soft()
        return
    for binary in ("paplay", "aplay"):
        if _try_player(binary, wav):
            return
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
            timeout=_TONE_TIMEOUT_SECONDS,
            check=False,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        _logger.warning(
            "All tone players failed at %d Hz; falling back to soft beep",
            frequency,
            exc_info=True,
        )
        _beep_soft()


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


def _max_fans() -> bool:
    """Ramp every NCT pwm channel to 100% speed via the helper script.

    The helper records prior state under /run/wake-alarm-fans.state so
    _restore_fans() can put things back without arguments. Safe: higher fan
    speed only lowers temperatures, never damages hardware.

    Returns:
        True when the ramp script ran successfully, False otherwise.
    """
    if _find_fan_hwmon() is None:
        return False
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
        return False
    if result.returncode != 0:
        _logger.warning(
            "Fan script %s exited %d: %s",
            _FAN_SCRIPT,
            result.returncode,
            result.stderr.decode(errors="replace").strip(),
        )
        return False
    return True


def _restore_fans(*, active: bool) -> None:
    """Restore fan speed if _max_fans() previously succeeded."""
    if not active:
        return
    try:
        subprocess.run(
            [_SUDO_BIN, "-n", _FAN_SCRIPT, "restore"],
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
    """Play a medium beep (sine tone via paplay/aplay/speaker-test)."""
    _play_tone(frequency)


def _beep_loud(frequency: int = 1000) -> None:
    """Play a loud sine tone via paplay/aplay/speaker-test."""
    _play_tone(frequency)


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

        self._current_code = _generate_code()
        self._skip_earnable: bool = True
        self._build_ui()
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
            self._dismiss_alarm(earned_skip=self._skip_earnable)
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
        _restore_fans(active=self._fan_state)
        _restore_alarm_audio(self._audio_restore)
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


def _pactl_path() -> str | None:
    """Return the absolute path to pactl, or None when not installed."""
    return shutil.which("pactl")


def _alarm_sink_present(pactl: str) -> bool:
    """Return True when the dedicated alarm HDMI sink exists in PipeWire."""
    try:
        result = subprocess.run(
            [pactl, "list", "short", "sinks"],
            capture_output=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        _logger.warning("pactl list sinks failed", exc_info=True)
        return False
    return ALARM_AUDIO_SINK in result.stdout.decode(errors="replace")


def _current_default_sink(pactl: str) -> str | None:
    """Return the current default sink name, or None on failure / empty."""
    try:
        result = subprocess.run(
            [pactl, "get-default-sink"],
            capture_output=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        _logger.warning("pactl get-default-sink failed", exc_info=True)
        return None
    name = result.stdout.decode(errors="replace").strip()
    return name or None


def _activate_alarm_audio() -> str | None:
    """Force the monitor's HDMI output on and route the alarm to it.

    At wake time the Bluetooth speaker is disconnected and PipeWire only has the
    ``auto_null`` sink, so the alarm is silent. This forces the HDMI card
    profile on, waits for its sink to appear, makes it the default sink, and
    raises it to full volume - empirically the only output audible on this
    machine at wake time (the G27Q monitor's built-in speaker).

    Returns:
        The previous default sink name (to restore on close), or ``None`` when
        the alarm audio sink could not be activated.
    """
    pactl = _pactl_path()
    if pactl is None:
        _logger.warning("pactl not on PATH; cannot activate alarm audio")
        return None
    subprocess.run(
        [pactl, "set-card-profile", ALARM_AUDIO_CARD, ALARM_AUDIO_PROFILE],
        capture_output=True,
        timeout=3,
        check=False,
    )
    attempts = max(
        1,
        int(ALARM_AUDIO_SINK_WAIT_SECONDS / ALARM_AUDIO_SINK_POLL_SECONDS),
    )
    for _ in range(attempts):
        if _alarm_sink_present(pactl):
            break
        time.sleep(ALARM_AUDIO_SINK_POLL_SECONDS)
    else:
        _logger.warning(
            "Alarm audio sink %s did not appear after %.0fs; alarm may be silent",
            ALARM_AUDIO_SINK,
            ALARM_AUDIO_SINK_WAIT_SECONDS,
        )
        return None
    old_default = _current_default_sink(pactl)
    for cmd in (
        [pactl, "set-default-sink", ALARM_AUDIO_SINK],
        [pactl, "set-sink-mute", ALARM_AUDIO_SINK, "0"],
        [pactl, "set-sink-volume", ALARM_AUDIO_SINK, "100%"],
    ):
        subprocess.run(cmd, capture_output=True, timeout=3, check=False)
    _logger.warning("Alarm audio routed to %s at 100%%", ALARM_AUDIO_SINK)
    return old_default


def _restore_alarm_audio(old_default: str | None) -> None:
    """Restore the default sink captured by :func:`_activate_alarm_audio`."""
    if old_default is None:
        return
    pactl = _pactl_path()
    if pactl is None:
        return
    subprocess.run(
        [pactl, "set-default-sink", old_default],
        capture_output=True,
        timeout=3,
        check=False,
    )


def _warn_if_no_real_sink() -> None:
    """Log a loud warning if PipeWire only has the auto_null sink."""
    pactl = _pactl_path()
    if pactl is None:
        _logger.warning("pactl not on PATH; cannot verify audio sinks")
        return
    try:
        result = subprocess.run(
            [pactl, "list", "short", "sinks"],
            capture_output=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        _logger.warning("pactl list sinks failed", exc_info=True)
        return
    sinks_text = result.stdout.decode(errors="replace").strip()
    sink_names = [
        line.split("\t")[1] for line in sinks_text.splitlines() if "\t" in line
    ]
    real_sinks = [s for s in sink_names if s != "auto_null"]
    if not real_sinks:
        _logger.warning(
            "ONLY auto_null PipeWire sink available \u2014 alarm will be SILENT. "
            "Sinks: %s",
            sink_names or "<none>",
        )
    else:
        _logger.info("Audio sinks available: %s", sink_names)


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
