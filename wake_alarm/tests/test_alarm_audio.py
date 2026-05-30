"""Tests for _audio.py — audio playback, fan control, and sink management."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator
    import pathlib

from python_pkg.wake_alarm._audio import (
    _beep_pcspkr,
    _ensure_tone_wav,
    _play_tone,
    _set_max_brightness,
    _try_player,
)


class TestSetMaxBrightness:
    """Tests for _set_max_brightness."""

    def test_noop_when_xrandr_missing(self) -> None:
        """No xrandr on PATH → subprocess.run never called."""
        with (
            patch("python_pkg.wake_alarm._audio.shutil.which", return_value=None),
            patch("python_pkg.wake_alarm._audio.subprocess.run") as mock_run,
        ):
            _set_max_brightness()
            mock_run.assert_not_called()

    def test_noop_on_oserror_from_query(self) -> None:
        """OSError from xrandr --query is suppressed."""
        with (
            patch(
                "python_pkg.wake_alarm._audio.shutil.which",
                return_value="/usr/bin/xrandr",
            ),
            patch(
                "python_pkg.wake_alarm._audio.subprocess.run",
                side_effect=OSError("no display"),
            ),
        ):
            _set_max_brightness()  # must not raise

    def test_noop_on_timeout_from_query(self) -> None:
        """TimeoutExpired from xrandr --query is suppressed."""
        with (
            patch(
                "python_pkg.wake_alarm._audio.shutil.which",
                return_value="/usr/bin/xrandr",
            ),
            patch(
                "python_pkg.wake_alarm._audio.subprocess.run",
                side_effect=subprocess.TimeoutExpired("xrandr", 5),
            ),
        ):
            _set_max_brightness()  # must not raise

    def test_sets_brightness_for_connected_displays(self) -> None:
        """Connected displays each get an --output --brightness call."""
        mock_query_result = MagicMock()
        mock_query_result.stdout = (
            "HDMI-0 connected 2560x1440+0+0\nDP-0 connected primary\n"
        )
        call_args_list: list[list[str]] = []

        def fake_run(args: list[str], **_kwargs: object) -> MagicMock:
            call_args_list.append(args)
            return mock_query_result

        with (
            patch(
                "python_pkg.wake_alarm._audio.shutil.which",
                return_value="/usr/bin/xrandr",
            ),
            patch("python_pkg.wake_alarm._audio.subprocess.run", side_effect=fake_run),
        ):
            _set_max_brightness()

        # First call is --query; subsequent calls set brightness for each output.
        brightness_calls = [a for a in call_args_list if "--brightness" in a]
        expected_brightness_calls = 2
        assert len(brightness_calls) == expected_brightness_calls

    def test_skips_disconnected_outputs(self) -> None:
        """Disconnected outputs do NOT get a brightness call."""
        mock_result = MagicMock()
        mock_result.stdout = "Screen 0: minimum 320\nHDMI-0 disconnected\n"
        with (
            patch(
                "python_pkg.wake_alarm._audio.shutil.which",
                return_value="/usr/bin/xrandr",
            ),
            patch(
                "python_pkg.wake_alarm._audio.subprocess.run",
                return_value=mock_result,
            ) as mock_run,
        ):
            _set_max_brightness()
        # Only the --query call, no brightness calls.
        assert mock_run.call_count == 1

    def test_warns_when_brightness_call_fails(self) -> None:
        """OSError on per-output --brightness call is logged but swallowed."""
        query_result = MagicMock()
        query_result.stdout = (
            "Screen 0: minimum 320\nHDMI-0 connected primary 1920x1080\n"
        )

        def _run_side_effect(args: list[str], **_kwargs: object) -> MagicMock:
            if "--query" in args:
                return query_result
            msg = "permission denied"
            raise OSError(msg)

        with (
            patch(
                "python_pkg.wake_alarm._audio.shutil.which",
                return_value="/usr/bin/xrandr",
            ),
            patch(
                "python_pkg.wake_alarm._audio.subprocess.run",
                side_effect=_run_side_effect,
            ),
        ):
            _set_max_brightness()  # must not raise


class TestEnsureToneWav:
    """Tests for _ensure_tone_wav (sine WAV generator + cache)."""

    def test_generates_and_caches(self, tmp_path: pathlib.Path) -> None:
        """First call generates the WAV; second call returns the cached path."""
        from python_pkg.wake_alarm import _audio as alarm_mod

        alarm_mod._TONE_CACHE.clear()
        with patch(
            "python_pkg.wake_alarm._audio.tempfile.gettempdir",
            return_value=str(tmp_path),
        ):
            path1 = _ensure_tone_wav(440)
            assert path1.exists()
            size = path1.stat().st_size
            assert size > 0
            # Second call must hit the cache (no regeneration).
            with patch("python_pkg.wake_alarm._audio.wave.open") as mock_open:
                path2 = _ensure_tone_wav(440)
                mock_open.assert_not_called()
            assert path2 == path1
        alarm_mod._TONE_CACHE.clear()

    def test_regenerates_when_cached_file_missing(
        self,
        tmp_path: pathlib.Path,
    ) -> None:
        """If the cached file was deleted, regenerate it."""
        from python_pkg.wake_alarm._audio import _TONE_CACHE

        _TONE_CACHE.clear()
        with patch(
            "python_pkg.wake_alarm._audio.tempfile.gettempdir",
            return_value=str(tmp_path),
        ):
            path1 = _ensure_tone_wav(880)
            path1.unlink()
            path2 = _ensure_tone_wav(880)
            assert path2.exists()
        _TONE_CACHE.clear()


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
            "python_pkg.wake_alarm._audio.shutil.which",
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
                "python_pkg.wake_alarm._audio.shutil.which",
                return_value="/usr/bin/paplay",
            ),
            patch(
                "python_pkg.wake_alarm._audio.subprocess.run",
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
                "python_pkg.wake_alarm._audio.shutil.which",
                return_value="/usr/bin/paplay",
            ),
            patch(
                "python_pkg.wake_alarm._audio.subprocess.run",
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
                "python_pkg.wake_alarm._audio.shutil.which",
                return_value="/usr/bin/paplay",
            ),
            patch(
                "python_pkg.wake_alarm._audio.subprocess.run",
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
                "python_pkg.wake_alarm._audio.shutil.which",
                return_value="/usr/bin/paplay",
            ),
            patch(
                "python_pkg.wake_alarm._audio.subprocess.run",
                side_effect=OSError("nope"),
            ),
        ):
            assert _try_player("paplay", wav) is False


class TestBeepPcspkr:
    """Tests for _beep_pcspkr (evdev PC speaker)."""

    def test_writes_tone_then_zero_to_device(self) -> None:
        """Successful path writes start-frequency then stop event."""

        mock_dev = MagicMock()
        mock_open_ctx = MagicMock()
        mock_open_ctx.__enter__.return_value = mock_dev
        mock_open_ctx.__exit__.return_value = False
        with (
            patch(
                "python_pkg.wake_alarm._audio.Path.open",
                return_value=mock_open_ctx,
            ),
            patch("python_pkg.wake_alarm._audio.time.sleep"),
        ):
            _beep_pcspkr(1000, 0.05)
        # First write carries the frequency, second write carries 0 (stop).
        assert mock_dev.write.call_count == 2

    def test_oserror_is_swallowed(self) -> None:
        """OSError opening the device must not raise."""

        with patch(
            "python_pkg.wake_alarm._audio.Path.open",
            side_effect=OSError("no device"),
        ):
            _beep_pcspkr(1000, 0.05)  # must not raise


class TestPlayTone:
    """Tests for _play_tone."""

    @pytest.fixture(autouse=True)
    def _silence_pcspkr(self) -> Iterator[None]:
        """Stop tests from hitting the real /dev/input PC speaker device."""
        with patch("python_pkg.wake_alarm._audio._beep_pcspkr"):
            yield

    def test_paplay_success_short_circuits(self, tmp_path: pathlib.Path) -> None:
        """If paplay succeeds, no further players are tried."""
        wav = tmp_path / "tone.wav"
        wav.write_bytes(b"\x00")
        with (
            patch(
                "python_pkg.wake_alarm._audio._ensure_tone_wav",
                return_value=wav,
            ),
            patch(
                "python_pkg.wake_alarm._audio._try_player",
                return_value=True,
            ) as mock_try,
            patch(
                "python_pkg.wake_alarm._audio.subprocess.run",
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
                "python_pkg.wake_alarm._audio._ensure_tone_wav",
                return_value=wav,
            ),
            patch(
                "python_pkg.wake_alarm._audio._try_player",
                return_value=False,
            ),
            patch(
                "python_pkg.wake_alarm._audio._speaker_test_path",
                return_value="/usr/bin/speaker-test",
            ),
            patch(
                "python_pkg.wake_alarm._audio.subprocess.run",
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
                "python_pkg.wake_alarm._audio._ensure_tone_wav",
                return_value=wav,
            ),
            patch(
                "python_pkg.wake_alarm._audio._try_player",
                return_value=False,
            ),
            patch(
                "python_pkg.wake_alarm._audio._speaker_test_path",
                side_effect=FileNotFoundError("missing"),
            ),
            patch("python_pkg.wake_alarm._audio._beep_soft") as mock_soft,
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
                "python_pkg.wake_alarm._audio._ensure_tone_wav",
                return_value=wav,
            ),
            patch(
                "python_pkg.wake_alarm._audio._try_player",
                return_value=False,
            ),
            patch(
                "python_pkg.wake_alarm._audio._speaker_test_path",
                return_value="/usr/bin/speaker-test",
            ),
            patch(
                "python_pkg.wake_alarm._audio.subprocess.run",
                side_effect=subprocess.TimeoutExpired("speaker-test", 6),
            ),
            patch("python_pkg.wake_alarm._audio._beep_soft") as mock_soft,
        ):
            _play_tone(800)
            mock_soft.assert_called_once()

    def test_soft_beep_when_wav_generation_fails(self) -> None:
        """OSError generating WAV → soft beep."""
        with (
            patch(
                "python_pkg.wake_alarm._audio._ensure_tone_wav",
                side_effect=OSError("disk full"),
            ),
            patch("python_pkg.wake_alarm._audio._beep_soft") as mock_soft,
        ):
            _play_tone(440)
            mock_soft.assert_called_once()
