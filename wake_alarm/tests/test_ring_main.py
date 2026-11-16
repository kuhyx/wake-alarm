"""The user-side ring entry the root ALSA script falls back to."""

from __future__ import annotations

from pathlib import Path
import signal
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from wake_alarm import _ring_main
from wake_alarm._ring_main import main

if TYPE_CHECKING:
    import pytest

if TYPE_CHECKING:
    from collections.abc import Callable

WAVS = ["rise.wav", "loop.wav"]


def _backend(*, start: tuple[bool, str] = (True, "ok"), pumps: list[bool]) -> MagicMock:
    backend = MagicMock()
    backend.name = "pipewire"
    backend.start.return_value = start
    backend.pump.side_effect = pumps
    return backend


def _run(backend: MagicMock, argv: list[str] | None = None) -> tuple[int, MagicMock]:
    with (
        patch.object(_ring_main, "PipeWireBackend", return_value=backend),
        patch.object(_ring_main, "configure_logging"),
        patch.object(_ring_main, "emit") as emitted,
        patch.object(_ring_main.time, "sleep"),
    ):
        return main(WAVS if argv is None else argv), emitted


def test_start_failure_emits_failed_and_exits_1() -> None:
    backend = _backend(start=(False, "no pw"), pumps=[])
    code, emitted = _run(backend)
    assert code == 1
    assert "FAILED" in emitted.call_args.args[1]
    backend.stop.assert_not_called()


def test_pump_failure_exits_1_and_stops() -> None:
    backend = _backend(pumps=[True, False])
    code, emitted = _run(backend)
    assert code == 1
    assert "started" in emitted.call_args_list[0].args[1]
    # pw-play dying mid-ring is a failure the audit must see, not silence.
    assert "FAILED" in emitted.call_args.args[1]
    assert emitted.call_args.kwargs["started"] is False
    backend.stop.assert_called_once()


def test_sigterm_ends_the_ring_cleanly() -> None:
    backend = _backend(pumps=[True, True])
    handler: list[Callable[..., object]] = []

    def capture(sig: int, fn: Callable[..., object]) -> None:
        assert sig == signal.SIGTERM
        handler.append(fn)

    def stop_after_first(_: float) -> None:
        handler[0](signal.SIGTERM, None)

    with (
        patch.object(_ring_main.signal, "signal", capture),
        patch.object(_ring_main, "PipeWireBackend", return_value=backend),
        patch.object(_ring_main, "configure_logging"),
        patch.object(_ring_main, "emit"),
        patch.object(_ring_main.time, "sleep", stop_after_first),
    ):
        assert main(WAVS) == 0
    backend.stop.assert_called_once()


def test_wrong_usage_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["only-one"]) == 2
    assert "Usage" in capsys.readouterr().err


def test_paths_reach_the_backend() -> None:
    backend = _backend(pumps=[False])
    with (
        patch.object(_ring_main, "PipeWireBackend", return_value=backend) as cls,
        patch.object(_ring_main, "configure_logging"),
        patch.object(_ring_main, "emit"),
    ):
        main(WAVS)
    cls.assert_called_once_with(Path("rise.wav"), Path("loop.wav"))
