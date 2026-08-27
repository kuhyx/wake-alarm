"""Bring the machine's hardware up before the alarm window appears.

Split out of ``_alarm.py`` for the 250-line cap.

Nothing here blocks waiting for the monitor. It powers things on and returns;
the beep loop's per-cycle sink check and ``_reactivate``'s retry schedule pick
up outputs as they enumerate, which is a real presence check rather than a
timed guess. The curtains are the same shape: fire and forget, never block.
"""

from __future__ import annotations

from collections.abc import Callable
import logging
import time

from wake_alarm._alarm_display import _wake_display
from wake_alarm._brightness import _set_max_brightness
from wake_alarm._constants import PLUG_PREROLL_SECONDS
from wake_alarm._curtains import open_curtains
from wake_alarm._sinks import _warn_if_no_real_sink
from wake_alarm._smart_plug import turn_on_plug

_logger = logging.getLogger(__name__)

_Sleep = Callable[[float], object]


def prepare_hardware(*, sleep: _Sleep = time.sleep) -> None:
    """Wake the display, raise brightness and power the speakers.

    Args:
        sleep: Delay function, injected so tests do not really wait.
    """
    _warn_if_no_real_sink()
    _wake_display()
    _set_max_brightness()
    # Power the speakers BEFORE the first beep. An amplifier's soft-start /
    # mute relay swallows the first seconds of audio after mains is applied,
    # so firing the plug and the first tone together loses the opening of the
    # alarm entirely. Costs nothing when no plug is configured.
    turn_on_plug()
    # Daylight is the one wake cue that outlives the audio failsafe: the sound
    # stops at FAILSAFE_SILENCE_SECONDS, an open curtain does not. No-op until
    # hardware exists, but the call site and the log event are real now.
    open_curtains()
    _logger.info(
        "Waiting %.1fs for speaker soft-start before the first beep",
        PLUG_PREROLL_SECONDS,
        extra={"event": "plug_preroll", "seconds": PLUG_PREROLL_SECONDS},
    )
    sleep(PLUG_PREROLL_SECONDS)
