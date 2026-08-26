"""Tests for the background beep loop."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING
from unittest.mock import patch

from wake_alarm._beep_loop import run_beep_loop, start_beep_thread
from wake_alarm._constants import (
    FAILSAFE_SILENCE_SECONDS,
    PHASE_MEDIUM_END,
    PHASE_SOFT_END,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    import pytest


class _Clock:
    """Monotonic stand-in that advances a fixed step on every read."""

    def __init__(self, start: float, step: float) -> None:
        self._now = start
        self._step = step

    def __call__(self) -> float:
        value = self._now
        self._now += self._step
        return value


def _run_once(elapsed: float) -> dict[str, int]:
    """Run exactly one loop iteration at *elapsed* seconds and count the calls."""
    stop = threading.Event()
    counts = {"soft": 0, "medium": 0, "loud": 0, "sinks": 0}

    def _count(key: str) -> Callable[..., None]:
        def _inner(*_a: object, **_k: object) -> None:
            counts[key] += 1
            stop.set()

        return _inner

    with (
        patch("wake_alarm._beep_loop._beep_soft", side_effect=_count("soft")),
        patch("wake_alarm._beep_loop._beep_medium", side_effect=_count("medium")),
        patch("wake_alarm._beep_loop._beep_loud", side_effect=_count("loud")),
        patch(
            "wake_alarm._beep_loop._play_on_all_sinks",
            side_effect=lambda *_a: counts.__setitem__("sinks", counts["sinks"] + 1),
        ),
    ):
        run_beep_loop(stop, 0.0, monotonic=lambda: elapsed)
    return counts


def test_exits_immediately_when_already_stopped() -> None:
    """A stop set before entry means no sound at all."""
    stop = threading.Event()
    stop.set()
    with patch("wake_alarm._beep_loop._play_on_all_sinks") as mock_play:
        run_beep_loop(stop, 0.0, monotonic=lambda: 0.0)
    mock_play.assert_not_called()


def test_soft_phase_uses_the_soft_beep() -> None:
    """Early in the ring the gentle tone sounds."""
    assert _run_once(0.0)["soft"] == 1


def test_medium_phase_uses_the_medium_beep() -> None:
    """The middle band uses the medium tone."""
    midpoint = (PHASE_SOFT_END + PHASE_MEDIUM_END) / 2 * 60
    assert _run_once(midpoint)["medium"] == 1


def test_loud_phase_uses_the_loud_beep() -> None:
    """Past the medium boundary the alarm is at its most insistent."""
    assert _run_once(PHASE_MEDIUM_END * 60 + 1)["loud"] == 1


def test_plays_on_every_sink_while_audible() -> None:
    """Audio is driven to all outputs, not one chosen sink."""
    assert _run_once(0.0)["sinks"] == 1


def test_failsafe_plays_no_audio() -> None:
    """Past the failsafe nothing sounds -- on any output."""
    stop = threading.Event()
    calls = {"n": 0}

    def _stop_after(*_a: object, **_k: object) -> None:
        calls["n"] += 1
        stop.set()

    ticks = {"n": 0}

    def _wait(_timeout: float) -> bool:
        # Nothing sounds during the failsafe, so no audio callback can end the
        # loop; stop it from the wait instead.
        ticks["n"] += 1
        if ticks["n"] >= 3:
            stop.set()
        return stop.is_set()

    with (
        patch("wake_alarm._beep_loop._play_on_all_sinks", side_effect=_stop_after),
        patch("wake_alarm._beep_loop._beep_soft", side_effect=_stop_after),
        patch("wake_alarm._beep_loop._beep_medium", side_effect=_stop_after),
        patch("wake_alarm._beep_loop._beep_loud", side_effect=_stop_after),
        patch.object(stop, "wait", _wait),
    ):
        run_beep_loop(
            stop,
            0.0,
            monotonic=_Clock(FAILSAFE_SILENCE_SECONDS, 1.0),
        )
    assert calls["n"] == 0
    assert ticks["n"] == 3


def test_failsafe_is_announced_once(caplog: pytest.LogCaptureFixture) -> None:
    """Reaching the failsafe is logged loudly, and only once."""
    stop = threading.Event()
    clock = _Clock(FAILSAFE_SILENCE_SECONDS, 1.0)
    ticks = {"n": 0}

    def _wait(_timeout: float) -> bool:
        ticks["n"] += 1
        if ticks["n"] >= 3:
            stop.set()
        return stop.is_set()

    with (
        caplog.at_level("WARNING"),
        patch.object(stop, "wait", _wait),
    ):
        run_beep_loop(stop, 0.0, monotonic=clock)
    assert caplog.text.count("Failsafe reached") == 1


def test_start_beep_thread_is_a_daemon() -> None:
    """A stuck beep thread must never keep the process alive."""
    stop = threading.Event()
    stop.set()
    thread = start_beep_thread(stop, 0.0)
    thread.join(timeout=5)
    assert thread.daemon
