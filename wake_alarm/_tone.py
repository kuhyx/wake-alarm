"""Synthesise and cache the alarm tone.

Split out of ``_audio.py`` for the 250-line cap.

Note the pylint ``generated-members`` entries for ``wave.Wave_write`` in
pyproject.toml: pylint infers the read-mode overload of ``wave.open`` and
wrongly reports ``setnchannels`` and friends as missing. Keep them.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
import struct
import tempfile
import wave

_logger = logging.getLogger(__name__)

# Generated WAVs are reused for the life of the process.
_TONE_CACHE: dict[int, Path] = {}
_TONE_DURATION_SECONDS: float = 1.5
_TONE_FRAMERATE: int = 48000
_TONE_AMPLITUDE: int = 32760  # near s16 max for the loudest sine we can emit


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
