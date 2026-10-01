"""The ring loop: polling cadence, backend fallback, always silenced."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from wake_alarm import _fallback_ring
from wake_alarm._fallback_ring import BACKEND_FAILED, Cadence, ring

if TYPE_CHECKING:
    from collections.abc import Iterator

RISE, LOOP = Path("rise.wav"), Path("loop.wav")


class FakeBackend:
    def __init__(self, name: str, *, start_ok: bool = True, pumps: int = 10**6) -> None:
        self.name = name
        self.start_ok = start_ok
        self.pumps_left = pumps
        self.stopped = 0

    def start(self) -> tuple[bool, str]:
        return self.start_ok, "detail"

    def pump(self) -> bool:
        self.pumps_left -= 1
        return self.pumps_left >= 0

    def stop(self) -> None:
        self.stopped += 1


class Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += seconds


def _polls(*answers: str | None) -> Iterator[str | None]:
    return iter(answers)


def _ring(backend: FakeBackend, answers: Iterator[str | None], clock: Clock) -> str:
    with patch.object(_fallback_ring, "select_backend", return_value=(backend, "why")):
        return ring(
            lambda: next(answers),
            rise=RISE,
            loop=LOOP,
            cadence=Cadence(clock, clock.sleep, 20),
        )


def test_polls_every_20_seconds_until_a_stop_reason(
    caplog: pytest.LogCaptureFixture,
) -> None:
    clock, backend = Clock(), FakeBackend("pipewire")
    with caplog.at_level(logging.INFO):
        assert _ring(backend, _polls(None, None, "session_started"), clock) == (
            "session_started"
        )
    assert clock.t == pytest.approx(60, abs=1)
    assert backend.stopped == 1
    assert "ring_backend: pipewire (started)" in caplog.text


def test_pipewire_refusing_falls_back_to_alsa() -> None:
    alsa = FakeBackend("alsa")
    with patch.object(_fallback_ring, "AlsaUnitBackend", return_value=alsa):
        alsa.name = "alsa"
        result = _ring(FakeBackend("pipewire", start_ok=False), _polls("cap"), Clock())
    assert result == "cap"
    assert alsa.stopped == 1


def test_no_backend_at_all() -> None:
    alsa = FakeBackend("alsa", start_ok=False)
    with patch.object(_fallback_ring, "AlsaUnitBackend", return_value=alsa):
        assert _ring(alsa, _polls(), Clock()) == BACKEND_FAILED


def test_pipewire_dying_mid_ring_hands_over_to_alsa() -> None:
    pipewire, alsa = FakeBackend("pipewire", pumps=3), FakeBackend("alsa")
    with patch.object(_fallback_ring, "AlsaUnitBackend", return_value=alsa):
        assert _ring(pipewire, _polls("escape"), Clock()) == "escape"
    assert pipewire.stopped == 1
    assert alsa.stopped == 1


def test_alsa_dying_mid_ring_ends_the_ring() -> None:
    alsa = FakeBackend("alsa", pumps=2)
    assert _ring(alsa, _polls(None), Clock()) == BACKEND_FAILED
    assert alsa.stopped >= 1


def test_replacement_alsa_failing_ends_the_ring() -> None:
    pipewire, alsa = (
        FakeBackend("pipewire", pumps=1),
        FakeBackend("alsa", start_ok=False),
    )
    with patch.object(_fallback_ring, "AlsaUnitBackend", return_value=alsa):
        assert _ring(pipewire, _polls(), Clock()) == BACKEND_FAILED


def test_an_exception_still_silences_the_backend() -> None:
    backend = FakeBackend("pipewire")

    def poll() -> str | None:
        raise SystemExit(143)

    clock = Clock()
    with (
        patch.object(_fallback_ring, "select_backend", return_value=(backend, "w")),
        pytest.raises(SystemExit),
    ):
        ring(poll, rise=RISE, loop=LOOP, cadence=Cadence(clock, clock.sleep, 0))
    assert backend.stopped == 1
