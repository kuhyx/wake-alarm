"""Mutable state the alarm carries while it is ringing.

Split out of ``_alarm.py`` for the 250-line cap. Kept as plain dataclasses so
the alarm's own module stays about behaviour rather than bookkeeping.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import subprocess

    from wake_alarm._challenges import _Challenge
    from wake_alarm._sinks import _AudioState


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
    """Machine state the alarm takes at start and gives back when it closes.

    Both fields are released together in ``on_close()``, so they live together:
    the audio routing the alarm rewrote, and the logind inhibitor holding the
    power button down while it rings.
    """

    audio_restore: _AudioState | None
    inhibitor: subprocess.Popen[bytes] | None = None
