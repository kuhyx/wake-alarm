"""Keep retrying card-profile activation while the alarm rings.

The bug this exists to fix, measured on the host:

    $ pactl list cards | grep -A1 'alsa_card.pci-0000_01_00.1'
    Active Profile: off
    $ pactl list short sinks
    61  alsa_output.pci-0000_0d_00.6.analog-stereo   IDLE

The G27Q's HDMI sink is simply **absent** while its card profile is ``off``,
so re-enumerating sinks every beep cycle can never find it -- there is nothing
to find. Only re-running ``set-card-profile`` brings the sink into existence.

At wake time the monitor has not finished its HDMI handshake, so the profile
reads ``available: no``, ``_parse_profile_line`` drops it, and the card is
never revisited. One activation pass at startup is therefore not enough: the
retry has to keep going for as long as an output might still be arriving.

Bounded and non-blocking: a background thread with a decaying schedule, so the
beep loop is never delayed by a card that will never appear.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
import logging
import threading
import time

from wake_alarm._constants import REACTIVATE_ATTEMPT_DELAYS
from wake_alarm._sinks import _activate_all_outputs, _list_real_sinks, _pactl_path

_Activate = Callable[[], object]
_ListSinks = Callable[[], Iterable[str]]
_Sleep = Callable[[float], object]

_logger = logging.getLogger(__name__)


def _attempt(
    activate: _Activate, list_sinks: _ListSinks, attempt: int
) -> frozenset[str]:
    """Run one activation pass and report the sinks that resulted.

    Args:
        activate: Callable re-running card-profile activation.
        list_sinks: Callable returning the current real sink names.
        attempt: 1-based attempt number, for the log line.

    Returns:
        The set of sink names visible after this pass.
    """
    activate()
    sinks = frozenset(list_sinks())
    _logger.info(
        "Sink reactivation pass %d: %d sink(s) present: %s",
        attempt,
        len(sinks),
        ", ".join(sorted(sinks)) or "(none)",
        extra={"sinks": sorted(sinks), "attempt": attempt},
    )
    return sinks


def reactivate_until_stable(
    activate: _Activate,
    list_sinks: _ListSinks,
    *,
    sleep: _Sleep,
    stop: threading.Event | None = None,
) -> frozenset[str]:
    """Re-run activation on a decaying schedule, logging what appears.

    Every pass is logged with the full enumerated sink list, so a future
    silent alarm can be diagnosed from the JSONL log instead of guessed at.

    Args:
        activate: Callable re-running card-profile activation.
        list_sinks: Callable returning the current real sink names.
        sleep: Callable delaying between passes (injected for tests).
        stop: Set once the alarm is dismissed, to end retrying early.

    Returns:
        The sink set observed on the final pass.
    """
    seen = _attempt(activate, list_sinks, 1)
    for index, delay in enumerate(REACTIVATE_ATTEMPT_DELAYS, start=2):
        if stop is not None and stop.is_set():
            break
        sleep(delay)
        if stop is not None and stop.is_set():
            break
        current = _attempt(activate, list_sinks, index)
        gained = current - seen
        if gained:
            _logger.warning(
                "New audio output(s) appeared %s into the alarm: %s",
                "late",
                ", ".join(sorted(gained)),
                extra={"gained": sorted(gained)},
            )
        seen = current
    return seen


def start_background_reactivation(
    activate: _Activate,
    list_sinks: _ListSinks,
    *,
    sleep: _Sleep,
    stop: threading.Event,
) -> threading.Thread:
    """Run :func:`reactivate_until_stable` on a daemon thread.

    Args:
        activate: Callable re-running card-profile activation.
        list_sinks: Callable returning the current real sink names.
        sleep: Callable delaying between passes.
        stop: Set once the alarm is dismissed.

    Returns:
        The started thread.
    """
    thread = threading.Thread(
        target=reactivate_until_stable,
        args=(activate, list_sinks),
        kwargs={"sleep": sleep, "stop": stop},
        daemon=True,
        name="wake-alarm-reactivate",
    )
    thread.start()
    return thread


def _activate_outputs_only() -> None:
    """Re-run card-profile activation, discarding the captured prior state.

    The return value of :func:`_activate_all_outputs` is the audio state as it
    was *before* that call, and only the very first call sees the user's real
    settings -- every retry pass captures the alarm's own already-activated
    state. Restoring one of those would restore the alarm's settings as if they
    were the user's, so the retries deliberately return nothing at all rather
    than handing back a value someone could later wire into ``on_close()``.
    """
    _activate_all_outputs()


def _list_real_sinks_now() -> list[str]:
    """Return the currently visible real sinks, or none when pactl is absent.

    :func:`wake_alarm._sinks._list_real_sinks` needs the pactl path, which is
    resolved fresh each pass: the retry outlives the startup lookup, and a
    machine without pactl must report "no sinks" rather than raise on a
    background thread nobody is watching.
    """
    pactl = _pactl_path()
    if pactl is None:
        return []
    return _list_real_sinks(pactl)


def start_alarm_reactivation(stop: threading.Event) -> threading.Thread:
    """Start the real reactivation retry for a ringing alarm.

    The wiring point: everything above takes injected callables so it can be
    tested without an audio stack, and this is the one place that binds them to
    the real ``pactl``.

    Args:
        stop: The alarm's beep-stop event, set once it is dismissed.

    Returns:
        The started daemon thread.
    """
    return start_background_reactivation(
        _activate_outputs_only,
        _list_real_sinks_now,
        sleep=time.sleep,
        stop=stop,
    )
