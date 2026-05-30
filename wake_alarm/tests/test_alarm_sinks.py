"""Tests for sink management and parse_args in wake alarm."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from python_pkg.wake_alarm._alarm import _parse_args
from python_pkg.wake_alarm._audio import (
    _activate_alarm_audio,
    _alarm_sink_present,
    _current_default_sink,
    _restore_alarm_audio,
    _warn_if_no_real_sink,
)


class TestWarnIfNoRealSink:
    """Tests for _warn_if_no_real_sink."""

    def test_logs_when_pactl_missing(self) -> None:
        """No pactl on PATH → warns and returns."""
        with (
            patch(
                "python_pkg.wake_alarm._audio.shutil.which",
                return_value=None,
            ),
            patch(
                "python_pkg.wake_alarm._audio.subprocess.run",
            ) as mock_run,
        ):
            _warn_if_no_real_sink()
            mock_run.assert_not_called()

    def test_warns_when_only_auto_null(self) -> None:
        """Only auto_null sink → warning is emitted."""
        result = MagicMock()
        result.stdout = b"4319\tauto_null\tPipeWire\tfloat32le 2ch 48000Hz\tIDLE\n"
        with (
            patch(
                "python_pkg.wake_alarm._audio.shutil.which",
                return_value="/usr/bin/pactl",
            ),
            patch(
                "python_pkg.wake_alarm._audio.subprocess.run",
                return_value=result,
            ),
            patch("python_pkg.wake_alarm._audio._logger") as mock_log,
        ):
            _warn_if_no_real_sink()
            mock_log.warning.assert_called()

    def test_info_when_real_sink_present(self) -> None:
        """A non-auto_null sink → info log, no warning."""
        result = MagicMock()
        result.stdout = b"1\talsa_output.pci-0000_01_00.1.hdmi-stereo\tPipeWire\t-\t-\n"
        with (
            patch(
                "python_pkg.wake_alarm._audio.shutil.which",
                return_value="/usr/bin/pactl",
            ),
            patch(
                "python_pkg.wake_alarm._audio.subprocess.run",
                return_value=result,
            ),
            patch("python_pkg.wake_alarm._audio._logger") as mock_log,
        ):
            _warn_if_no_real_sink()
            mock_log.info.assert_called()
            mock_log.warning.assert_not_called()

    def test_handles_pactl_failure(self) -> None:
        """OSError/TimeoutExpired running pactl → warning, no raise."""
        with (
            patch(
                "python_pkg.wake_alarm._audio.shutil.which",
                return_value="/usr/bin/pactl",
            ),
            patch(
                "python_pkg.wake_alarm._audio.subprocess.run",
                side_effect=subprocess.TimeoutExpired("pactl", 5),
            ),
        ):
            _warn_if_no_real_sink()  # must not raise


class TestAlarmSinkPresent:
    """Tests for _alarm_sink_present."""

    def test_true_when_sink_listed(self) -> None:
        """Returns True when the alarm sink name appears in pactl output."""
        from python_pkg.wake_alarm._constants import ALARM_AUDIO_SINK

        proc = MagicMock(stdout=ALARM_AUDIO_SINK.encode() + b"\tPipeWire\n")
        with patch(
            "python_pkg.wake_alarm._audio.subprocess.run",
            return_value=proc,
        ):
            assert _alarm_sink_present("/usr/bin/pactl") is True

    def test_false_when_sink_absent(self) -> None:
        """Returns False when the alarm sink is not in pactl output."""
        proc = MagicMock(stdout=b"auto_null\tPipeWire\n")
        with patch(
            "python_pkg.wake_alarm._audio.subprocess.run",
            return_value=proc,
        ):
            assert _alarm_sink_present("/usr/bin/pactl") is False

    def test_false_on_subprocess_error(self) -> None:
        """OSError while listing sinks → False, no raise."""
        with patch(
            "python_pkg.wake_alarm._audio.subprocess.run",
            side_effect=OSError("boom"),
        ):
            assert _alarm_sink_present("/usr/bin/pactl") is False


class TestCurrentDefaultSink:
    """Tests for _current_default_sink."""

    def test_returns_sink_name(self) -> None:
        """Returns the trimmed default sink name."""
        proc = MagicMock(stdout=b"jbl_sink\n")
        with patch(
            "python_pkg.wake_alarm._audio.subprocess.run",
            return_value=proc,
        ):
            assert _current_default_sink("/usr/bin/pactl") == "jbl_sink"

    def test_returns_none_when_empty(self) -> None:
        """Empty output → None."""
        proc = MagicMock(stdout=b"\n")
        with patch(
            "python_pkg.wake_alarm._audio.subprocess.run",
            return_value=proc,
        ):
            assert _current_default_sink("/usr/bin/pactl") is None

    def test_returns_none_on_error(self) -> None:
        """TimeoutExpired → None, no raise."""
        with patch(
            "python_pkg.wake_alarm._audio.subprocess.run",
            side_effect=subprocess.TimeoutExpired("pactl", 3),
        ):
            assert _current_default_sink("/usr/bin/pactl") is None


class TestActivateAlarmAudio:
    """Tests for _activate_alarm_audio."""

    def test_returns_none_when_pactl_missing(self) -> None:
        """No pactl on PATH → returns None without touching audio."""
        with (
            patch("python_pkg.wake_alarm._audio.shutil.which", return_value=None),
            patch("python_pkg.wake_alarm._audio.subprocess.run") as mock_run,
        ):
            assert _activate_alarm_audio() is None
            mock_run.assert_not_called()

    def test_activates_and_returns_old_default(self) -> None:
        """Sink present → routes audio there and returns prior default sink."""
        with (
            patch(
                "python_pkg.wake_alarm._audio.shutil.which",
                return_value="/usr/bin/pactl",
            ),
            patch(
                "python_pkg.wake_alarm._audio._alarm_sink_present",
                return_value=True,
            ),
            patch(
                "python_pkg.wake_alarm._audio._current_default_sink",
                return_value="jbl_sink",
            ),
            patch("python_pkg.wake_alarm._audio.subprocess.run") as mock_run,
        ):
            result = _activate_alarm_audio()
        assert result == "jbl_sink"
        cmds = [call.args[0] for call in mock_run.call_args_list]
        from python_pkg.wake_alarm._constants import (
            ALARM_AUDIO_CARD,
            ALARM_AUDIO_PROFILE,
            ALARM_AUDIO_SINK,
        )

        assert [
            "/usr/bin/pactl",
            "set-card-profile",
            ALARM_AUDIO_CARD,
            ALARM_AUDIO_PROFILE,
        ] in cmds
        assert ["/usr/bin/pactl", "set-default-sink", ALARM_AUDIO_SINK] in cmds

    def test_returns_none_when_sink_never_appears(self) -> None:
        """Sink never shows up → returns None after polling (no raise)."""
        with (
            patch(
                "python_pkg.wake_alarm._audio.shutil.which",
                return_value="/usr/bin/pactl",
            ),
            patch(
                "python_pkg.wake_alarm._audio._alarm_sink_present",
                return_value=False,
            ),
            patch("python_pkg.wake_alarm._audio.time.sleep") as mock_sleep,
            patch("python_pkg.wake_alarm._audio.subprocess.run"),
        ):
            assert _activate_alarm_audio() is None
            mock_sleep.assert_called()

    def test_waits_then_succeeds(self) -> None:
        """Sink absent then present → sleeps once, then routes audio."""
        with (
            patch(
                "python_pkg.wake_alarm._audio.shutil.which",
                return_value="/usr/bin/pactl",
            ),
            patch(
                "python_pkg.wake_alarm._audio._alarm_sink_present",
                side_effect=[False, True],
            ),
            patch(
                "python_pkg.wake_alarm._audio._current_default_sink",
                return_value="old",
            ),
            patch("python_pkg.wake_alarm._audio.time.sleep") as mock_sleep,
            patch("python_pkg.wake_alarm._audio.subprocess.run"),
        ):
            assert _activate_alarm_audio() == "old"
            mock_sleep.assert_called_once()


class TestRestoreAlarmAudio:
    """Tests for _restore_alarm_audio."""

    def test_none_is_noop(self) -> None:
        """None default → does nothing, no pactl lookup."""
        with patch("python_pkg.wake_alarm._audio.shutil.which") as mock_which:
            _restore_alarm_audio(None)
            mock_which.assert_not_called()

    def test_no_pactl_returns_silently(self) -> None:
        """Default present but pactl missing → no raise, no run."""
        with (
            patch("python_pkg.wake_alarm._audio.shutil.which", return_value=None),
            patch("python_pkg.wake_alarm._audio.subprocess.run") as mock_run,
        ):
            _restore_alarm_audio("jbl_sink")
            mock_run.assert_not_called()

    def test_restores_default_sink(self) -> None:
        """Calls set-default-sink with the captured prior default."""
        with (
            patch(
                "python_pkg.wake_alarm._audio.shutil.which",
                return_value="/usr/bin/pactl",
            ),
            patch("python_pkg.wake_alarm._audio.subprocess.run") as mock_run,
        ):
            _restore_alarm_audio("jbl_sink")
        cmds = [call.args[0] for call in mock_run.call_args_list]
        assert ["/usr/bin/pactl", "set-default-sink", "jbl_sink"] in cmds


class TestParseArgs:
    """Tests for _parse_args."""

    def test_default_flags_are_false(self) -> None:
        """No CLI args means every flag is False."""
        ns = _parse_args([])
        assert ns.demo is False
        assert ns.trigger_now is False
        assert ns.production is False

    def test_flags_parse(self) -> None:
        """Each flag flips to True when passed."""
        ns = _parse_args(["--production", "--demo", "--trigger-now"])
        assert ns.production is True
        assert ns.demo is True
        assert ns.trigger_now is True
