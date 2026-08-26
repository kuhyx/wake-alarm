"""Tests for _audio.py — audio playback, fan control, and sink management."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator
    import pathlib

from wake_alarm._audio import (
    _play_tone,
    _try_player,
)


class TestTryPlayer:
    """Tests for _try_player."""

    def test_returns_false_when_binary_missing(
        self,
        tmp_path: pathlib.Path,
    ) -> None:
        """Missing binary returns False without raising."""
        wav = tmp_path / "x.wav"
        wav.write_bytes(b"\x00")
        with patch(
            "wake_alarm._audio.shutil.which",
            return_value=None,
        ):
            assert _try_player("paplay", wav) is False

    def test_returns_true_on_success(self, tmp_path: pathlib.Path) -> None:
        """Zero exit code returns True."""
        wav = tmp_path / "x.wav"
        wav.write_bytes(b"\x00")
        result = MagicMock()
        result.returncode = 0
        with (
            patch(
                "wake_alarm._audio.shutil.which",
                return_value="/usr/bin/paplay",
            ),
            patch(
                "wake_alarm._audio.subprocess.run",
                return_value=result,
            ),
        ):
            assert _try_player("paplay", wav) is True

    def test_returns_false_on_nonzero_exit(
        self,
        tmp_path: pathlib.Path,
    ) -> None:
        """Non-zero exit code returns False and logs."""
        wav = tmp_path / "x.wav"
        wav.write_bytes(b"\x00")
        result = MagicMock()
        result.returncode = 1
        result.stderr = b"boom"
        with (
            patch(
                "wake_alarm._audio.shutil.which",
                return_value="/usr/bin/paplay",
            ),
            patch(
                "wake_alarm._audio.subprocess.run",
                return_value=result,
            ),
        ):
            assert _try_player("paplay", wav) is False

    def test_returns_false_on_timeout(self, tmp_path: pathlib.Path) -> None:
        """TimeoutExpired returns False and logs."""
        wav = tmp_path / "x.wav"
        wav.write_bytes(b"\x00")
        with (
            patch(
                "wake_alarm._audio.shutil.which",
                return_value="/usr/bin/paplay",
            ),
            patch(
                "wake_alarm._audio.subprocess.run",
                side_effect=subprocess.TimeoutExpired("paplay", 6),
            ),
        ):
            assert _try_player("paplay", wav) is False

    def test_returns_false_on_oserror(self, tmp_path: pathlib.Path) -> None:
        """OSError returns False and logs."""
        wav = tmp_path / "x.wav"
        wav.write_bytes(b"\x00")
        with (
            patch(
                "wake_alarm._audio.shutil.which",
                return_value="/usr/bin/paplay",
            ),
            patch(
                "wake_alarm._audio.subprocess.run",
                side_effect=OSError("nope"),
            ),
        ):
            assert _try_player("paplay", wav) is False


class TestPlayTone:
    """Tests for _play_tone."""

    @pytest.fixture(autouse=True)
    def _silence_pcspkr(self) -> Iterator[None]:
        """Stop tests from hitting the real /dev/input PC speaker device."""
        with patch("wake_alarm._audio._beep_pcspkr"):
            yield

    def test_paplay_success_short_circuits(self, tmp_path: pathlib.Path) -> None:
        """If paplay succeeds, no further players are tried."""
        wav = tmp_path / "tone.wav"
        wav.write_bytes(b"\x00")
        with (
            patch(
                "wake_alarm._audio._ensure_tone_wav",
                return_value=wav,
            ),
            patch(
                "wake_alarm._audio._try_player",
                return_value=True,
            ) as mock_try,
            patch(
                "wake_alarm._audio.subprocess.run",
            ) as mock_run,
        ):
            _play_tone(440)
            mock_try.assert_called_once_with("paplay", wav)
            mock_run.assert_not_called()

    def test_falls_back_to_aplay_then_speaker_test(
        self,
        tmp_path: pathlib.Path,
    ) -> None:
        """paplay+aplay fail → speaker-test is tried."""
        wav = tmp_path / "tone.wav"
        wav.write_bytes(b"\x00")
        with (
            patch(
                "wake_alarm._audio._ensure_tone_wav",
                return_value=wav,
            ),
            patch(
                "wake_alarm._audio._try_player",
                return_value=False,
            ),
            patch(
                "wake_alarm._audio._speaker_test_path",
                return_value="/usr/bin/speaker-test",
            ),
            patch(
                "wake_alarm._audio.subprocess.run",
            ) as mock_run,
        ):
            _play_tone(1000)
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert "/usr/bin/speaker-test" in args
            assert "1000" in args

    def test_soft_beep_when_speaker_test_missing(
        self,
        tmp_path: pathlib.Path,
    ) -> None:
        """All players fail → soft beep."""
        wav = tmp_path / "tone.wav"
        wav.write_bytes(b"\x00")
        with (
            patch(
                "wake_alarm._audio._ensure_tone_wav",
                return_value=wav,
            ),
            patch(
                "wake_alarm._audio._try_player",
                return_value=False,
            ),
            patch(
                "wake_alarm._audio._speaker_test_path",
                side_effect=FileNotFoundError("missing"),
            ),
            patch("wake_alarm._audio._beep_soft") as mock_soft,
        ):
            _play_tone(800)
            mock_soft.assert_called_once()

    def test_soft_beep_when_speaker_test_times_out(
        self,
        tmp_path: pathlib.Path,
    ) -> None:
        """speaker-test TimeoutExpired → soft beep."""
        wav = tmp_path / "tone.wav"
        wav.write_bytes(b"\x00")
        with (
            patch(
                "wake_alarm._audio._ensure_tone_wav",
                return_value=wav,
            ),
            patch(
                "wake_alarm._audio._try_player",
                return_value=False,
            ),
            patch(
                "wake_alarm._audio._speaker_test_path",
                return_value="/usr/bin/speaker-test",
            ),
            patch(
                "wake_alarm._audio.subprocess.run",
                side_effect=subprocess.TimeoutExpired("speaker-test", 6),
            ),
            patch("wake_alarm._audio._beep_soft") as mock_soft,
        ):
            _play_tone(800)
            mock_soft.assert_called_once()

    def test_soft_beep_when_wav_generation_fails(self) -> None:
        """OSError generating WAV → soft beep."""
        with (
            patch(
                "wake_alarm._audio._ensure_tone_wav",
                side_effect=OSError("disk full"),
            ),
            patch("wake_alarm._audio._beep_soft") as mock_soft,
        ):
            _play_tone(440)
            mock_soft.assert_called_once()
