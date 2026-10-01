"""The generated ring sound."""

from __future__ import annotations

from typing import TYPE_CHECKING
import wave

from wake_alarm._ring_wav import (
    LOOP_FILENAME,
    RISE_FILENAME,
    SAMPLE_RATE,
    ensure_pair,
    main,
    samples,
    write_pair,
)

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _peak(data: list[int], start: float, seconds: float) -> int:
    lo = int(start * SAMPLE_RATE)
    return max(abs(v) for v in data[lo : lo + int(seconds * SAMPLE_RATE)])


def test_the_rise_climbs_then_holds_full_scale() -> None:
    data = list(samples(4.0, rise_seconds=2.0))
    first, middle, held = (
        _peak(data, 0, 0.5),
        _peak(data, 1.0, 0.5),
        _peak(data, 2.4, 1),
    )
    assert 0 < first < middle < held
    assert held > 30_000


def test_the_loop_is_full_scale_with_pauses() -> None:
    data = list(samples(1.2))
    assert _peak(data, 0, 0.12) > 30_000
    assert _peak(data, 0.85, 0.3) == 0  # the pause after four beeps


def test_write_pair_produces_valid_wavs(tmp_path: Path) -> None:
    rise, loop = write_pair(tmp_path / "out", rise_seconds=0.5, loop_seconds=0.25)
    with wave.open(str(rise)) as handle:
        assert (handle.getnchannels(), handle.getsampwidth()) == (1, 2)
        assert handle.getframerate() == SAMPLE_RATE
        assert handle.getnframes() == SAMPLE_RATE // 2
    with wave.open(str(loop)) as handle:
        assert handle.getnframes() == SAMPLE_RATE // 4


def test_ensure_pair_prefers_the_installed_copy(tmp_path: Path) -> None:
    system, user = tmp_path / "system", tmp_path / "user"
    system.mkdir()
    (system / RISE_FILENAME).write_bytes(b"r")
    (system / LOOP_FILENAME).write_bytes(b"l")
    assert ensure_pair(system, user) == (system / RISE_FILENAME, system / LOOP_FILENAME)


def test_ensure_pair_generates_when_nothing_is_installed(tmp_path: Path) -> None:
    rise, loop = ensure_pair(tmp_path / "system", tmp_path / "user")
    assert rise.parent == tmp_path / "user"
    assert rise.is_file()
    assert loop.is_file()
    # A second call reuses what the first generated.
    assert ensure_pair(tmp_path / "system", tmp_path / "user") == (rise, loop)


def test_cli_writes_into_the_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--write", str(tmp_path)]) == 0
    assert capsys.readouterr().out.splitlines() == [
        str(tmp_path / RISE_FILENAME),
        str(tmp_path / LOOP_FILENAME),
    ]


def test_cli_reads_sys_argv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["prog", "--write", str(tmp_path)])
    assert main() == 0
