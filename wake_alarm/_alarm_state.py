"""Mutable state the alarm carries while it is ringing.

Split out of ``_alarm.py`` for the 250-line cap. Kept as plain dataclasses so
the alarm's own module stays about behaviour rather than bookkeeping.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
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
    """Hardware state captured at alarm start, restored when it closes."""

    audio_restore: _AudioState | None
