"""The silent monitor probe: once, at A - 5, on a morning with no session.

On 2026-11-22 the fallback rang 30 minutes into the analog speakers, which
kuhy switches off at the knob for the night, so nothing was heard. The ring
now plays to every connected monitor too (``scripts/pc/ring_alsa.sh``).
Whether a monitor really takes the stream with no graphical session can be
known only in that state, and kuhy asked for no test sound, so this starts
``wake-alarm-ring-probe.service`` once: digital silence into each monitor,
one ``ring_probe`` journal line per sink. The first real fallback morning's
``ring_sink`` lines are the follow-up check.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from wake_alarm._constants import LOG_STATE_DIR
from wake_alarm._events import emit
from wake_alarm._ring_player import _ok, graphical_session

if TYPE_CHECKING:
    from datetime import datetime

PROBE_UNIT = "wake-alarm-ring-probe.service"
PROBE_DONE_FILE = LOG_STATE_DIR / "ring_probe_done"
PROBE_LEAD = timedelta(minutes=5)


def maybe_probe(now: datetime, alarm_at: datetime) -> str | None:
    """Start the probe if it is due; what happened, or None when not due."""
    if PROBE_DONE_FILE.exists() or not alarm_at - PROBE_LEAD <= now < alarm_at:
        return None
    graphical, why = graphical_session()
    if graphical:
        # Not the state a fallback ring meets; try again tomorrow.
        return "waiting_for_no_session"
    started, out = _ok(["sudo", "-n", "systemctl", "start", PROBE_UNIT])
    emit("ring_probe", "started" if started else "failed", session=why, output=out)
    if not started:
        return "failed"
    PROBE_DONE_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROBE_DONE_FILE.write_text(now.isoformat(), encoding="utf-8")
    return "started"
