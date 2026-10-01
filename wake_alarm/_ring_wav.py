"""The PC fallback alarm's sound, generated with stdlib ``wave``.

Two files, because the players can only loop a file from its start:

* ``ring.wav`` -- 60 s of the alarm pattern rising from about -26 dB to full
  scale (linear in dB, so it is heard as a steady climb);
* ``ring_loop.wav`` -- the same pattern at full scale, looped after the rise.

The pattern is a classic alarm: four short beeps alternating 880/1320 Hz with
a third harmonic for bite, then a pause. Generated, never committed (the
binary hook forbids it): ``install.sh`` writes the system copy, and the user
backend regenerates its own if that copy is missing.

    python -m wake_alarm._ring_wav --write /some/dir
"""

from __future__ import annotations

import argparse
from array import array
import math
from pathlib import Path
import struct
import sys
import wave

SAMPLE_RATE = 16_000
RISE_SECONDS = 60.0
LOOP_SECONDS = 20.0
RISE_FILENAME = "ring.wav"
LOOP_FILENAME = "ring_loop.wav"

# install.sh writes the pair here (world-readable, for the root ALSA unit and
# the user alike); the user backend falls back to generating its own copy.
SYSTEM_WAV_DIR = Path("/usr/local/share/wake-alarm")
USER_WAV_DIR = Path.home() / ".local" / "share" / "wake_alarm"

_FLOOR = 0.05  # -26 dB: audible at the start, never silent
_PEAK = 32_000  # just under int16 full scale, so the harmonic never clips
_BEEP = 0.12
_GAP = 0.08
_BEEPS = 4
_PERIOD = 1.2
_PITCHES = (880.0, 1320.0)


def _tone(t: float) -> float:
    """The alarm pattern at time ``t``, in ``[-1, 1]``."""
    phase = t % _PERIOD
    slot = int(phase // (_BEEP + _GAP))
    if slot >= _BEEPS or phase - slot * (_BEEP + _GAP) >= _BEEP:
        return 0.0
    pitch = _PITCHES[slot % len(_PITCHES)]
    angle = 2 * math.pi * pitch * t
    # 0.75 sin x + 0.25 sin 3x peaks at 1/sqrt(2); scale it to full scale.
    return math.sqrt(2) * (0.75 * math.sin(angle) + 0.25 * math.sin(3 * angle))


def _gain(t: float, rise_seconds: float) -> float:
    """Loudness at ``t``: the dB-linear climb, then full scale."""
    if rise_seconds <= 0 or t >= rise_seconds:
        return 1.0
    return float(_FLOOR * (1 / _FLOOR) ** (t / rise_seconds))


def samples(seconds: float, *, rise_seconds: float = 0.0) -> array[int]:
    """``seconds`` of 16-bit mono samples, rising over ``rise_seconds``."""
    out = array("h")
    for index in range(int(seconds * SAMPLE_RATE)):
        t = index / SAMPLE_RATE
        out.append(round(_PEAK * _gain(t, rise_seconds) * _tone(t)))
    return out


def write_wav(path: Path, data: array[int]) -> None:
    """Write ``data`` as a 16 kHz mono 16-bit WAV at ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # WAV is little-endian whatever the host is; pack explicitly.
    frames = struct.pack(f"<{len(data)}h", *data)
    with wave.Wave_write(str(path)) as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(frames)


def write_pair(
    directory: Path,
    *,
    rise_seconds: float = RISE_SECONDS,
    loop_seconds: float = LOOP_SECONDS,
) -> tuple[Path, Path]:
    """Write ``ring.wav`` and ``ring_loop.wav`` into ``directory``."""
    rise, loop = directory / RISE_FILENAME, directory / LOOP_FILENAME
    write_wav(rise, samples(rise_seconds, rise_seconds=rise_seconds))
    write_wav(loop, samples(loop_seconds))
    return rise, loop


def ensure_pair(preferred: Path, fallback: Path) -> tuple[Path, Path]:
    """The installed pair if both exist, else a pair generated in ``fallback``."""
    for directory in (preferred, fallback):
        rise, loop = directory / RISE_FILENAME, directory / LOOP_FILENAME
        if rise.is_file() and loop.is_file():
            return rise, loop
    return write_pair(fallback)


def main(argv: list[str] | None = None) -> int:
    """Write the pair into ``--write DIR``."""
    parser = argparse.ArgumentParser(description="Generate the fallback ring WAVs")
    parser.add_argument("--write", type=Path, required=True, metavar="DIR")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    for path in write_pair(args.write):
        sys.stdout.write(f"{path}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
