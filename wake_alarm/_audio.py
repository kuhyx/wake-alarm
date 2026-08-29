"""Audio playback and PipeWire sink management for the wake alarm."""

from __future__ import annotations

import logging
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import time

from wake_alarm._sinks import (
    _ensure_sink_audible,
    _list_real_sinks,
    _pactl_path,
)
from wake_alarm._tone import _ensure_tone_wav

_logger = logging.getLogger(__name__)

_TONE_TIMEOUT_SECONDS: float = 6.0
_TONE_DURATION_SECONDS: float = 1.5

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
    except OSError, subprocess.TimeoutExpired:
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
    except FileNotFoundError, OSError, subprocess.TimeoutExpired:
        _logger.warning(
            "All tone players failed at %d Hz; falling back to soft beep",
            frequency,
            exc_info=True,
        )
        _beep_soft()


def _play_on_all_sinks(frequency: int) -> None:
    """Play the tone WAV on every real PipeWire sink, simultaneously.

    Re-enumerates sinks on every call so outputs that appear late (the G27Q
    HDMI sink can take ~15 s to power on) are automatically included without
    re-running activation. All sinks are launched concurrently, then reaped so
    the 30-minute alarm loop does not accumulate zombie ``paplay`` children.
    """
    pactl = _pactl_path()
    if pactl is None:
        return
    paplay = shutil.which("paplay")
    if paplay is None:
        _logger.warning("paplay not on PATH; skipping per-sink alarm playback")
        return
    try:
        wav = _ensure_tone_wav(frequency)
    except OSError:
        _logger.warning(
            "Could not generate tone WAV at %d Hz for per-sink playback",
            frequency,
            exc_info=True,
        )
        return
    procs: list[subprocess.Popen[bytes]] = []
    for sink in _list_real_sinks(pactl):
        # Re-assert audibility every cycle: a source that is muted, low, or only
        # just appeared (a monitor powering on mid-alarm) is made audible before
        # we play on it — we never bet on one sink staying the chosen output.
        _ensure_sink_audible(pactl, sink)
        proc = _play_wav_on_sink(paplay, sink, wav)
        if proc is not None:
            procs.append(proc)
    _reap_players(procs)


def _play_wav_on_sink(
    paplay: str,
    sink: str,
    wav: Path,
) -> subprocess.Popen[bytes] | None:
    """Launch ``paplay --device=<sink>`` for *wav*; return the process or None."""
    try:
        return subprocess.Popen(
            [paplay, f"--device={sink}", str(wav)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        _logger.warning("Failed to play tone on sink %s", sink, exc_info=True)
        return None


def _reap_players(procs: list[subprocess.Popen[bytes]]) -> None:
    """Wait for each concurrent paplay to finish, killing any that hang.

    The tone is ~1.5 s, so all launched players finish quickly and are reaped
    here rather than left as ``<defunct>`` children for the alarm's lifetime.
    """
    for proc in procs:
        _reap_player(proc)


def _reap_player(proc: subprocess.Popen[bytes]) -> None:
    """Wait for one paplay process, killing and reaping it if it hangs."""
    try:
        proc.wait(timeout=_TONE_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        _logger.warning("paplay hung; killing pid %d", proc.pid)
        proc.kill()
        proc.wait()


def _beep_medium(frequency: int = 1000) -> None:
    """Play a medium beep (sine tone via paplay/aplay/speaker-test)."""
    _play_tone(frequency)


def _beep_loud(frequency: int = 1000) -> None:
    """Play a loud sine tone via paplay/aplay/speaker-test."""
    _play_tone(frequency)
