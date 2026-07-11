"""Tests for per-sink alarm playback (_play_on_all_sinks and helpers)."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from wake_alarm._audio import _play_on_all_sinks, _play_wav_on_sink, _reap_players
from wake_alarm._sinks import _ensure_sink_audible

if TYPE_CHECKING:
    from pathlib import Path


class TestPlayOnAllSinks:
    """Tests for _play_on_all_sinks."""

    def test_noop_when_pactl_missing(self) -> None:
        """No pactl → returns without looking up paplay or spawning Popen."""
        with (
            patch("wake_alarm._audio._pactl_path", return_value=None),
            patch("wake_alarm._audio.shutil.which") as mock_which,
            patch("wake_alarm._audio.subprocess.Popen") as mock_popen,
        ):
            _play_on_all_sinks(1000)
            mock_which.assert_not_called()
            mock_popen.assert_not_called()

    def test_warns_when_paplay_missing(self) -> None:
        """pactl present but paplay absent → warning, no Popen."""
        with (
            patch("wake_alarm._audio._pactl_path", return_value="/usr/bin/pactl"),
            patch("wake_alarm._audio.shutil.which", return_value=None),
            patch("wake_alarm._audio.subprocess.Popen") as mock_popen,
        ):
            _play_on_all_sinks(1000)
            mock_popen.assert_not_called()

    def test_returns_when_wav_generation_fails(self) -> None:
        """OSError generating the tone WAV → returns, no Popen."""
        with (
            patch("wake_alarm._audio._pactl_path", return_value="/usr/bin/pactl"),
            patch("wake_alarm._audio.shutil.which", return_value="/usr/bin/paplay"),
            patch(
                "wake_alarm._audio._ensure_tone_wav",
                side_effect=OSError("no tempdir"),
            ),
            patch("wake_alarm._audio.subprocess.Popen") as mock_popen,
        ):
            _play_on_all_sinks(1000)
            mock_popen.assert_not_called()

    def test_plays_and_maxes_each_sink(self, tmp_path: Path) -> None:
        """Each real sink is made audible, then played on via paplay --device."""
        wav = tmp_path / "tone.wav"
        with (
            patch("wake_alarm._audio._pactl_path", return_value="/usr/bin/pactl"),
            patch("wake_alarm._audio.shutil.which", return_value="/usr/bin/paplay"),
            patch("wake_alarm._audio._ensure_tone_wav", return_value=wav),
            patch(
                "wake_alarm._audio._list_real_sinks",
                return_value=["sink_a", "sink_b"],
            ),
            patch("wake_alarm._audio._ensure_sink_audible") as mock_audible,
            patch("wake_alarm._audio.subprocess.Popen") as mock_popen,
        ):
            _play_on_all_sinks(1000)
        assert mock_audible.call_count == 2
        devices = [call.args[0][1] for call in mock_popen.call_args_list]
        assert devices == ["--device=sink_a", "--device=sink_b"]

    def test_skips_sink_whose_launch_failed(self) -> None:
        """A sink whose paplay fails to launch (None) is not reaped."""
        with (
            patch("wake_alarm._audio._pactl_path", return_value="/usr/bin/pactl"),
            patch("wake_alarm._audio.shutil.which", return_value="/usr/bin/paplay"),
            patch("wake_alarm._audio._ensure_tone_wav", return_value=MagicMock()),
            patch("wake_alarm._audio._list_real_sinks", return_value=["sink_a"]),
            patch("wake_alarm._audio._ensure_sink_audible"),
            patch("wake_alarm._audio._play_wav_on_sink", return_value=None),
            patch("wake_alarm._audio._reap_players") as mock_reap,
        ):
            _play_on_all_sinks(1000)
        mock_reap.assert_called_once_with([])


class TestReapPlayers:
    """Tests for _reap_players."""

    def test_waits_for_each(self) -> None:
        """Each launched paplay is waited on (reaped)."""
        procs = [MagicMock(), MagicMock()]
        _reap_players(procs)
        for proc in procs:
            proc.wait.assert_called_once()

    def test_kills_hung_player(self) -> None:
        """A paplay that exceeds the timeout is killed and then reaped."""
        proc = MagicMock()
        proc.wait.side_effect = [subprocess.TimeoutExpired("paplay", 6), None]
        _reap_players([proc])
        proc.kill.assert_called_once()
        assert proc.wait.call_count == 2


class TestEnsureSinkAudible:
    """Tests for _ensure_sink_audible."""

    def test_unmutes_and_maxes(self) -> None:
        """Runs set-sink-mute 0 then set-sink-volume 100% for the sink."""
        with patch("wake_alarm._sinks.subprocess.run") as mock_run:
            _ensure_sink_audible("/usr/bin/pactl", "sink_a")
        cmds = [call.args[0] for call in mock_run.call_args_list]
        assert ["/usr/bin/pactl", "set-sink-mute", "sink_a", "0"] in cmds
        assert ["/usr/bin/pactl", "set-sink-volume", "sink_a", "100%"] in cmds


class TestPlayWavOnSink:
    """Tests for _play_wav_on_sink."""

    def test_spawns_paplay_with_device(self, tmp_path: Path) -> None:
        """Popen is called with paplay --device=<sink> and the wav path."""
        with patch("wake_alarm._audio.subprocess.Popen") as mock_popen:
            _play_wav_on_sink("/usr/bin/paplay", "sink_a", tmp_path / "tone.wav")
        args = mock_popen.call_args.args[0]
        assert args[0] == "/usr/bin/paplay"
        assert args[1] == "--device=sink_a"

    def test_ignores_oserror(self, tmp_path: Path) -> None:
        """OSError from Popen is swallowed (must not raise)."""
        with patch(
            "wake_alarm._audio.subprocess.Popen",
            side_effect=OSError("device busy"),
        ):
            _play_wav_on_sink("/usr/bin/paplay", "sink_a", tmp_path / "tone.wav")
