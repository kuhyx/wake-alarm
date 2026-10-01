"""Ring until told to stop: the loop behind one fallback ring.

Owns only the noise and its lifetime. *Whether* to keep ringing is the
caller's ``poll`` (re-read every ``FALLBACK_POLL_SECONDS``), which returns a
stop reason or None. The backend is always stopped on the way out, however
the loop ends -- including the ``SystemExit`` a SIGTERM handler raises -- so
a dying tick can never leave the root ALSA unit playing (and the unit has its
own runtime cap for a tick that is SIGKILLed).

Cadence uses the monotonic clock; the 30-minute cap is the caller's, on the
wall clock, because the monotonic clock does not advance through S4.
"""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import TYPE_CHECKING

from wake_alarm._events import emit
from wake_alarm._fallback_policy import FALLBACK_POLL_SECONDS
from wake_alarm._ring_player import AlsaUnitBackend, Backend, select_backend

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

BACKEND_FAILED = "backend_failed"
_PUMP_SECONDS = 1.0


def _start(rise: Path, loop: Path) -> Backend | None:
    """Pick and start a backend, falling back to ALSA if PipeWire refuses."""
    backend, why = select_backend(rise, loop)
    started, detail = backend.start()
    if not started and backend.name != AlsaUnitBackend.name:
        why = f"{why}; {backend.name} failed: {detail}"
        backend = AlsaUnitBackend()
        started, detail = backend.start()
    emit(
        "ring_backend",
        f"{backend.name} ({'started' if started else 'FAILED'})",
        backend=backend.name,
        why=why,
        started=started,
        detail=detail,
    )
    return backend if started else None


def _switch_to_alsa(failed: Backend) -> Backend | None:
    """PipeWire died mid-ring: silence it and hand over to the root unit."""
    failed.stop()
    if failed.name == AlsaUnitBackend.name:
        return None
    backend = AlsaUnitBackend()
    started, detail = backend.start()
    emit(
        "ring_backend",
        f"alsa after {failed.name} died ({'started' if started else 'FAILED'})",
        backend=backend.name,
        why=f"{failed.name} stopped playing mid-ring",
        started=started,
        detail=detail,
    )
    return backend if started else None


@dataclass(frozen=True)
class Cadence:
    """How the loop keeps time; injectable so tests never really wait."""

    clock: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep
    poll_seconds: float = FALLBACK_POLL_SECONDS


def ring(
    poll: Callable[[], str | None],
    *,
    rise: Path,
    loop: Path,
    cadence: Cadence | None = None,
) -> str:
    """Ring until ``poll`` names a stop reason; returns that reason.

    Returns ``backend_failed`` when no backend could make a sound.
    """
    tick = cadence or Cadence()
    backend = _start(rise, loop)
    if backend is None:
        return BACKEND_FAILED
    try:
        next_poll = tick.clock() + tick.poll_seconds
        while True:
            if not backend.pump():
                replacement = _switch_to_alsa(backend)
                if replacement is None:
                    return BACKEND_FAILED
                backend = replacement
            if tick.clock() >= next_poll:
                reason = poll()
                if reason is not None:
                    return reason
                next_poll = tick.clock() + tick.poll_seconds
            tick.sleep(_PUMP_SECONDS)
    finally:
        backend.stop()
