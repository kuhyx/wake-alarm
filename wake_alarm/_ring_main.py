"""The user-side ring the root ALSA script falls back to.

``scripts/pc/ring_alsa.sh`` runs ``python -m wake_alarm._ring_main <rise>
<loop>`` as the user (``runuser``) the first time the speakers' card is busy:
PipeWire holds it, so the ring goes *through* PipeWire instead of fighting
it. Plays until SIGTERM (exit 0); exits 1 with ``ring_backend ... FAILED``
when PipeWire cannot play, which tells the script to try killing the holder.
"""

from __future__ import annotations

from pathlib import Path
import signal
import sys
import time

from wake_alarm._events import emit
from wake_alarm._logging_setup import configure_logging
from wake_alarm._ring_player import PipeWireBackend

_PUMP_SECONDS = 1.0
_ARGS = 2  # rise.wav, loop.wav


def main(argv: list[str] | None = None) -> int:
    """Ring through PipeWire until SIGTERM; 1 when it cannot, 2 on bad usage."""
    args = sys.argv[1:] if argv is None else argv
    if len(args) != _ARGS:
        sys.stderr.write("Usage: _ring_main <rise.wav> <loop.wav>\n")
        return 2
    configure_logging(component="ring")
    backend = PipeWireBackend(Path(args[0]), Path(args[1]))
    started, detail = backend.start()
    emit(
        "ring_backend",
        f"pipewire for root unit ({'started' if started else 'FAILED'})",
        backend=backend.name,
        why="root unit found the card busy",
        started=started,
        detail=detail,
    )
    if not started:
        return 1
    stopping: list[bool] = []
    signal.signal(signal.SIGTERM, lambda *_: stopping.append(True))
    try:
        while not stopping:
            if not backend.pump():
                # Dying mid-ring must reach the log as loudly as never starting.
                emit(
                    "ring_backend",
                    "pipewire for root unit (FAILED)",
                    backend=backend.name,
                    why="pw-play stopped mid-ring",
                    started=False,
                    detail="pump failed",
                )
                return 1
            time.sleep(_PUMP_SECONDS)
    finally:
        backend.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
