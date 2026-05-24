"""Tests for _alarm.py — wake alarm daemon, UI, and beep logic."""

from __future__ import annotations

import pathlib
import subprocess
import tkinter as tk
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

if TYPE_CHECKING:
    from collections.abc import Generator, Iterator

from python_pkg.wake_alarm._alarm import (
    _beep_loud,
    _beep_medium,
    _beep_pcspkr,
    _beep_soft,
    _ensure_tone_wav,
    _find_fan_hwmon,
    _generate_code,
    _is_alarm_day,
    _max_fans,
    _max_sink_volume,
    _parse_args,
    _play_on_extra_devices,
    _play_tone,
    _restore_display,
    _restore_fans,
    _restore_sink_volume,
    _set_max_brightness,
    _should_run_alarm,
    _speaker_test_path,
    _try_player,
    _wake_display,
    _warn_if_no_real_sink,
)
from python_pkg.wake_alarm._constants import (
    DISMISS_CODE_LENGTH,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_tk() -> MagicMock:
    """Build a MagicMock that stands in for the tkinter module."""
    mock = MagicMock()
    mock_root = MagicMock()
    mock_root.winfo_screenwidth.return_value = 1920
    mock_root.winfo_screenheight.return_value = 1080
    mock.Tk.return_value = mock_root
    mock.Frame.return_value = MagicMock()
    mock.Label.return_value = MagicMock()
    mock.Entry.return_value = MagicMock()
    mock.TclError = tk.TclError
    mock.END = tk.END
    return mock


@pytest.fixture(autouse=True)
def _block_real_tk() -> Generator[MagicMock]:
    """Prevent any real Tk windows in tests."""
    mock = _make_mock_tk()
    with patch("python_pkg.wake_alarm._alarm.tk", mock):
        yield mock


@pytest.fixture
def mock_tk_module() -> Generator[MagicMock]:
    """Provide explicit access to the mocked tk module."""
    mock = _make_mock_tk()
    with patch("python_pkg.wake_alarm._alarm.tk", mock):
        yield mock


# ---------------------------------------------------------------------------
# Unit tests for pure functions
# ---------------------------------------------------------------------------


class TestGenerateCode:
    """Tests for _generate_code."""

    def test_correct_length(self) -> None:
        """Generated code has the configured length."""
        code = _generate_code()
        assert len(code) == DISMISS_CODE_LENGTH

    def test_all_digits(self) -> None:
        """Generated code contains only digits."""
        code = _generate_code()
        assert code.isdigit()

    def test_different_codes(self) -> None:
        """Two calls produce different codes (probabilistic, but safe)."""
        codes = {_generate_code() for _ in range(50)}
        assert len(codes) > 1


class TestIsAlarmDay:
    """Tests for _is_alarm_day."""

    def test_monday_is_alarm_day(self) -> None:
        """Monday (weekday=0) is an alarm day."""
        from datetime import datetime

        # Create a date that is Monday
        with patch(
            "python_pkg.wake_alarm._alarm.datetime",
        ) as mock_dt:
            mock_now = MagicMock()
            mock_now.weekday.return_value = 0  # Monday
            mock_dt.now.return_value = mock_now
            mock_dt.side_effect = datetime
            assert _is_alarm_day() is True

    def test_tuesday_is_not_alarm_day(self) -> None:
        """Tuesday (weekday=1) is NOT an alarm day."""
        with patch(
            "python_pkg.wake_alarm._alarm.datetime",
        ) as mock_dt:
            mock_now = MagicMock()
            mock_now.weekday.return_value = 1  # Tuesday
            mock_dt.now.return_value = mock_now
            assert _is_alarm_day() is False

    def test_friday_is_alarm_day(self) -> None:
        """Friday (weekday=4) is an alarm day."""
        with patch(
            "python_pkg.wake_alarm._alarm.datetime",
        ) as mock_dt:
            mock_now = MagicMock()
            mock_now.weekday.return_value = 4  # Friday
            mock_dt.now.return_value = mock_now
            assert _is_alarm_day() is True

    def test_saturday_is_alarm_day(self) -> None:
        """Saturday (weekday=5) is an alarm day."""
        with patch(
            "python_pkg.wake_alarm._alarm.datetime",
        ) as mock_dt:
            mock_now = MagicMock()
            mock_now.weekday.return_value = 5
            mock_dt.now.return_value = mock_now
            assert _is_alarm_day() is True

    def test_sunday_is_alarm_day(self) -> None:
        """Sunday (weekday=6) is an alarm day."""
        with patch(
            "python_pkg.wake_alarm._alarm.datetime",
        ) as mock_dt:
            mock_now = MagicMock()
            mock_now.weekday.return_value = 6
            mock_dt.now.return_value = mock_now
            assert _is_alarm_day() is True

    def test_wednesday_is_not_alarm_day(self) -> None:
        """Wednesday (weekday=2) is NOT an alarm day."""
        with patch(
            "python_pkg.wake_alarm._alarm.datetime",
        ) as mock_dt:
            mock_now = MagicMock()
            mock_now.weekday.return_value = 2
            mock_dt.now.return_value = mock_now
            assert _is_alarm_day() is False


class TestSpeakerTestPath:
    """Tests for _speaker_test_path."""

    def test_returns_path_when_found(self) -> None:
        """Return full path when speaker-test is available."""
        with patch(
            "python_pkg.wake_alarm._alarm.shutil.which",
            return_value="/usr/bin/speaker-test",
        ):
            assert _speaker_test_path() == "/usr/bin/speaker-test"

    def test_raises_when_not_found(self) -> None:
        """Raise FileNotFoundError when speaker-test is missing."""
        with (
            patch(
                "python_pkg.wake_alarm._alarm.shutil.which",
                return_value=None,
            ),
            pytest.raises(FileNotFoundError, match="speaker-test not found"),
        ):
            _speaker_test_path()


class TestBeepFunctions:
    """Tests for beep helper functions."""

    def test_beep_soft_writes_bell(self) -> None:
        """_beep_soft writes terminal bell character."""
        with patch("python_pkg.wake_alarm._alarm.sys") as mock_sys:
            mock_sys.stdout = MagicMock()
            _beep_soft()
            mock_sys.stdout.write.assert_called_once_with("\a")
            mock_sys.stdout.flush.assert_called_once()

    def test_beep_medium_delegates_to_play_tone(self) -> None:
        """_beep_medium just delegates to _play_tone."""
        with patch("python_pkg.wake_alarm._alarm._play_tone") as mock_play:
            _beep_medium(frequency=800)
            mock_play.assert_called_once_with(800)

    def test_beep_loud_delegates_to_play_tone(self) -> None:
        """_beep_loud just delegates to _play_tone."""
        with patch("python_pkg.wake_alarm._alarm._play_tone") as mock_play:
            _beep_loud(frequency=1200)
            mock_play.assert_called_once_with(1200)


class TestShouldRunAlarm:
    """Tests for _should_run_alarm."""

    def test_returns_false_on_non_alarm_day(self) -> None:
        """Return False when today is not an alarm day."""
        with patch(
            "python_pkg.wake_alarm._alarm._is_alarm_day",
            return_value=False,
        ):
            assert _should_run_alarm() is False

    def test_returns_false_when_already_dismissed(self) -> None:
        """Return False when alarm was already dismissed today."""
        with (
            patch(
                "python_pkg.wake_alarm._alarm._is_alarm_day",
                return_value=True,
            ),
            patch(
                "python_pkg.wake_alarm._alarm.was_alarm_dismissed_today",
                return_value=True,
            ),
        ):
            assert _should_run_alarm() is False

    def test_returns_true_when_alarm_day_and_not_dismissed(self) -> None:
        """Return True when today is alarm day and not yet dismissed."""
        with (
            patch(
                "python_pkg.wake_alarm._alarm._is_alarm_day",
                return_value=True,
            ),
            patch(
                "python_pkg.wake_alarm._alarm.was_alarm_dismissed_today",
                return_value=False,
            ),
        ):
            assert _should_run_alarm() is True


class TestDisplayHelpers:
    """Tests for _wake_display and _restore_display when xset is absent."""

    def test_wake_display_skips_when_xset_missing(self) -> None:
        """_wake_display does nothing when xset is not on PATH."""
        with (
            patch(
                "python_pkg.wake_alarm._alarm.shutil.which",
                return_value=None,
            ),
            patch("python_pkg.wake_alarm._alarm.subprocess.run") as mock_run,
        ):
            _wake_display()
        mock_run.assert_not_called()

    def test_wake_display_runs_xset_commands(self) -> None:
        """_wake_display runs xset dpms force on + xset s off."""
        with (
            patch(
                "python_pkg.wake_alarm._alarm.shutil.which",
                return_value="/usr/bin/xset",
            ),
            patch("python_pkg.wake_alarm._alarm.subprocess.run") as mock_run,
        ):
            _wake_display()
        assert mock_run.call_count == 2
        call_args = [call[0][0] for call in mock_run.call_args_list]
        assert ["/usr/bin/xset", "dpms", "force", "on"] in call_args
        assert ["/usr/bin/xset", "s", "off"] in call_args

    def test_restore_display_skips_when_xset_missing(self) -> None:
        """_restore_display does nothing when xset is not on PATH."""
        with (
            patch(
                "python_pkg.wake_alarm._alarm.shutil.which",
                return_value=None,
            ),
            patch("python_pkg.wake_alarm._alarm.subprocess.run") as mock_run,
        ):
            _restore_display()
        mock_run.assert_not_called()


class TestPlayOnExtraDevices:
    """Tests for _play_on_extra_devices."""

    def test_popen_called_for_each_device(self) -> None:
        """_play_on_extra_devices spawns speaker-test with PIPEWIRE_NODE set."""
        with (
            patch(
                "python_pkg.wake_alarm._alarm._speaker_test_path",
                return_value="/usr/bin/speaker-test",
            ),
            patch("python_pkg.wake_alarm._alarm.subprocess.Popen") as mock_popen,
        ):
            _play_on_extra_devices(1000)
            mock_popen.assert_called_once()
            args = mock_popen.call_args[0][0]
            env = mock_popen.call_args.kwargs["env"]
            assert "/usr/bin/speaker-test" in args
            assert "-D" not in args
            assert "1000" in args
            assert "PIPEWIRE_NODE" in env
            assert "alsa_output" in env["PIPEWIRE_NODE"]

    def test_noop_when_speaker_test_missing(self) -> None:
        """_play_on_extra_devices does nothing when speaker-test is absent."""
        with (
            patch(
                "python_pkg.wake_alarm._alarm._speaker_test_path",
                side_effect=FileNotFoundError("not found"),
            ),
            patch("python_pkg.wake_alarm._alarm.subprocess.Popen") as mock_popen,
        ):
            _play_on_extra_devices(1000)
            mock_popen.assert_not_called()

    def test_ignores_oserror_on_popen(self) -> None:
        """_play_on_extra_devices silently ignores OSError from Popen."""
        with (
            patch(
                "python_pkg.wake_alarm._alarm._speaker_test_path",
                return_value="/usr/bin/speaker-test",
            ),
            patch(
                "python_pkg.wake_alarm._alarm.subprocess.Popen",
                side_effect=OSError("device busy"),
            ),
        ):
            _play_on_extra_devices(1000)  # must not raise


class TestFindFanHwmon:
    """Tests for _find_fan_hwmon."""

    def test_returns_none_when_no_hwmon(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """No hwmon entries → returns None."""
        monkeypatch.setattr(pathlib.Path, "glob", lambda _s, _p: iter([]))
        assert _find_fan_hwmon() is None

    def test_returns_none_for_unknown_chip(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Non-NCT chip name → returns None."""
        name_file = tmp_path / "name"
        name_file.write_text("unknown_chip\n")
        monkeypatch.setattr(pathlib.Path, "glob", lambda _s, _p: iter([name_file]))
        assert _find_fan_hwmon() is None

    def test_returns_hwmon_dir_for_nct_chip(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """NCT chip name → returns the hwmon directory path."""
        name_file = tmp_path / "name"
        name_file.write_text("nct6799\n")
        monkeypatch.setattr(pathlib.Path, "glob", lambda _s, _p: iter([name_file]))
        result = _find_fan_hwmon()
        assert result == str(tmp_path)

    def test_skips_unreadable_name_file(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """OSError on read → skips and returns None."""
        bad_path = MagicMock(spec=pathlib.Path)
        bad_path.read_text.side_effect = OSError("unreadable")
        monkeypatch.setattr(pathlib.Path, "glob", lambda _s, _p: iter([bad_path]))
        assert _find_fan_hwmon() is None


class TestMaxFans:
    """Tests for _max_fans."""

    def test_returns_false_when_no_hwmon(self) -> None:
        """No fan controller → returns False immediately."""
        with patch("python_pkg.wake_alarm._alarm._find_fan_hwmon", return_value=None):
            assert _max_fans() is False

    def test_returns_false_on_script_oserror(self, tmp_path: pathlib.Path) -> None:
        """OSError running fan script → returns False."""
        with (
            patch(
                "python_pkg.wake_alarm._alarm._find_fan_hwmon",
                return_value=str(tmp_path),
            ),
            patch(
                "python_pkg.wake_alarm._alarm.subprocess.run",
                side_effect=OSError("not found"),
            ),
        ):
            assert _max_fans() is False

    def test_returns_false_on_script_timeout(self, tmp_path: pathlib.Path) -> None:
        """TimeoutExpired running fan script → returns False."""
        with (
            patch(
                "python_pkg.wake_alarm._alarm._find_fan_hwmon",
                return_value=str(tmp_path),
            ),
            patch(
                "python_pkg.wake_alarm._alarm.subprocess.run",
                side_effect=subprocess.TimeoutExpired("fan", 5),
            ),
        ):
            assert _max_fans() is False

    def test_returns_false_on_nonzero_returncode(self, tmp_path: pathlib.Path) -> None:
        """Fan script exits non-zero → returns False."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        with (
            patch(
                "python_pkg.wake_alarm._alarm._find_fan_hwmon",
                return_value=str(tmp_path),
            ),
            patch(
                "python_pkg.wake_alarm._alarm.subprocess.run",
                return_value=mock_result,
            ),
        ):
            assert _max_fans() is False

    def test_returns_true_on_success(self, tmp_path: pathlib.Path) -> None:
        """Successful run → returns True (state is saved by the helper)."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        with (
            patch(
                "python_pkg.wake_alarm._alarm._find_fan_hwmon",
                return_value=str(tmp_path),
            ),
            patch(
                "python_pkg.wake_alarm._alarm.subprocess.run",
                return_value=mock_result,
            ),
        ):
            assert _max_fans() is True


class TestRestoreFans:
    """Tests for _restore_fans."""

    def test_noop_when_inactive(self) -> None:
        """False state → subprocess.run is never called."""
        with patch("python_pkg.wake_alarm._alarm.subprocess.run") as mock_run:
            _restore_fans(active=False)
            mock_run.assert_not_called()

    def test_calls_fan_script_restore(self) -> None:
        """Active state → fan script called with restore (no args)."""
        with patch("python_pkg.wake_alarm._alarm.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            _restore_fans(active=True)
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert "restore" in args

    def test_ignores_oserror_on_restore(self) -> None:
        """OSError from fan script is silently suppressed."""
        with patch(
            "python_pkg.wake_alarm._alarm.subprocess.run",
            side_effect=OSError("no script"),
        ):
            _restore_fans(active=True)  # must not raise

    def test_ignores_timeout_on_restore(self) -> None:
        """TimeoutExpired from fan script is silently suppressed."""
        with patch(
            "python_pkg.wake_alarm._alarm.subprocess.run",
            side_effect=subprocess.TimeoutExpired("fan", 5),
        ):
            _restore_fans(active=True)  # must not raise


class TestSetMaxBrightness:
    """Tests for _set_max_brightness."""

    def test_noop_when_xrandr_missing(self) -> None:
        """No xrandr on PATH → subprocess.run never called."""
        with (
            patch("python_pkg.wake_alarm._alarm.shutil.which", return_value=None),
            patch("python_pkg.wake_alarm._alarm.subprocess.run") as mock_run,
        ):
            _set_max_brightness()
            mock_run.assert_not_called()

    def test_noop_on_oserror_from_query(self) -> None:
        """OSError from xrandr --query is suppressed."""
        with (
            patch(
                "python_pkg.wake_alarm._alarm.shutil.which",
                return_value="/usr/bin/xrandr",
            ),
            patch(
                "python_pkg.wake_alarm._alarm.subprocess.run",
                side_effect=OSError("no display"),
            ),
        ):
            _set_max_brightness()  # must not raise

    def test_noop_on_timeout_from_query(self) -> None:
        """TimeoutExpired from xrandr --query is suppressed."""
        with (
            patch(
                "python_pkg.wake_alarm._alarm.shutil.which",
                return_value="/usr/bin/xrandr",
            ),
            patch(
                "python_pkg.wake_alarm._alarm.subprocess.run",
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
                "python_pkg.wake_alarm._alarm.shutil.which",
                return_value="/usr/bin/xrandr",
            ),
            patch("python_pkg.wake_alarm._alarm.subprocess.run", side_effect=fake_run),
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
                "python_pkg.wake_alarm._alarm.shutil.which",
                return_value="/usr/bin/xrandr",
            ),
            patch(
                "python_pkg.wake_alarm._alarm.subprocess.run",
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
                "python_pkg.wake_alarm._alarm.shutil.which",
                return_value="/usr/bin/xrandr",
            ),
            patch(
                "python_pkg.wake_alarm._alarm.subprocess.run",
                side_effect=_run_side_effect,
            ),
        ):
            _set_max_brightness()  # must not raise


class TestEnsureToneWav:
    """Tests for _ensure_tone_wav (sine WAV generator + cache)."""

    def test_generates_and_caches(self, tmp_path: pathlib.Path) -> None:
        """First call generates the WAV; second call returns the cached path."""
        from python_pkg.wake_alarm import _alarm as alarm_mod

        alarm_mod._TONE_CACHE.clear()
        with patch(
            "python_pkg.wake_alarm._alarm.tempfile.gettempdir",
            return_value=str(tmp_path),
        ):
            path1 = _ensure_tone_wav(440)
            assert path1.exists()
            size = path1.stat().st_size
            assert size > 0
            # Second call must hit the cache (no regeneration).
            with patch("python_pkg.wake_alarm._alarm.wave.open") as mock_open:
                path2 = _ensure_tone_wav(440)
                mock_open.assert_not_called()
            assert path2 == path1
        alarm_mod._TONE_CACHE.clear()

    def test_regenerates_when_cached_file_missing(
        self,
        tmp_path: pathlib.Path,
    ) -> None:
        """If the cached file was deleted, regenerate it."""
        from python_pkg.wake_alarm._alarm import _TONE_CACHE

        _TONE_CACHE.clear()
        with patch(
            "python_pkg.wake_alarm._alarm.tempfile.gettempdir",
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
            "python_pkg.wake_alarm._alarm.shutil.which",
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
                "python_pkg.wake_alarm._alarm.shutil.which",
                return_value="/usr/bin/paplay",
            ),
            patch(
                "python_pkg.wake_alarm._alarm.subprocess.run",
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
                "python_pkg.wake_alarm._alarm.shutil.which",
                return_value="/usr/bin/paplay",
            ),
            patch(
                "python_pkg.wake_alarm._alarm.subprocess.run",
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
                "python_pkg.wake_alarm._alarm.shutil.which",
                return_value="/usr/bin/paplay",
            ),
            patch(
                "python_pkg.wake_alarm._alarm.subprocess.run",
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
                "python_pkg.wake_alarm._alarm.shutil.which",
                return_value="/usr/bin/paplay",
            ),
            patch(
                "python_pkg.wake_alarm._alarm.subprocess.run",
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
                "python_pkg.wake_alarm._alarm.Path.open",
                return_value=mock_open_ctx,
            ),
            patch("python_pkg.wake_alarm._alarm.time.sleep"),
        ):
            _beep_pcspkr(1000, 0.05)
        # First write carries the frequency, second write carries 0 (stop).
        assert mock_dev.write.call_count == 2

    def test_oserror_is_swallowed(self) -> None:
        """OSError opening the device must not raise."""

        with patch(
            "python_pkg.wake_alarm._alarm.Path.open",
            side_effect=OSError("no device"),
        ):
            _beep_pcspkr(1000, 0.05)  # must not raise


class TestPlayTone:
    """Tests for _play_tone."""

    @pytest.fixture(autouse=True)
    def _silence_pcspkr(self) -> Iterator[None]:
        """Stop tests from hitting the real /dev/input PC speaker device."""
        with patch("python_pkg.wake_alarm._alarm._beep_pcspkr"):
            yield

    def test_paplay_success_short_circuits(self, tmp_path: pathlib.Path) -> None:
        """If paplay succeeds, no further players are tried."""
        wav = tmp_path / "tone.wav"
        wav.write_bytes(b"\x00")
        with (
            patch(
                "python_pkg.wake_alarm._alarm._ensure_tone_wav",
                return_value=wav,
            ),
            patch(
                "python_pkg.wake_alarm._alarm._try_player",
                return_value=True,
            ) as mock_try,
            patch(
                "python_pkg.wake_alarm._alarm.subprocess.run",
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
                "python_pkg.wake_alarm._alarm._ensure_tone_wav",
                return_value=wav,
            ),
            patch(
                "python_pkg.wake_alarm._alarm._try_player",
                return_value=False,
            ),
            patch(
                "python_pkg.wake_alarm._alarm._speaker_test_path",
                return_value="/usr/bin/speaker-test",
            ),
            patch(
                "python_pkg.wake_alarm._alarm.subprocess.run",
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
                "python_pkg.wake_alarm._alarm._ensure_tone_wav",
                return_value=wav,
            ),
            patch(
                "python_pkg.wake_alarm._alarm._try_player",
                return_value=False,
            ),
            patch(
                "python_pkg.wake_alarm._alarm._speaker_test_path",
                side_effect=FileNotFoundError("missing"),
            ),
            patch("python_pkg.wake_alarm._alarm._beep_soft") as mock_soft,
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
                "python_pkg.wake_alarm._alarm._ensure_tone_wav",
                return_value=wav,
            ),
            patch(
                "python_pkg.wake_alarm._alarm._try_player",
                return_value=False,
            ),
            patch(
                "python_pkg.wake_alarm._alarm._speaker_test_path",
                return_value="/usr/bin/speaker-test",
            ),
            patch(
                "python_pkg.wake_alarm._alarm.subprocess.run",
                side_effect=subprocess.TimeoutExpired("speaker-test", 6),
            ),
            patch("python_pkg.wake_alarm._alarm._beep_soft") as mock_soft,
        ):
            _play_tone(800)
            mock_soft.assert_called_once()

    def test_soft_beep_when_wav_generation_fails(self) -> None:
        """OSError generating WAV → soft beep."""
        with (
            patch(
                "python_pkg.wake_alarm._alarm._ensure_tone_wav",
                side_effect=OSError("disk full"),
            ),
            patch("python_pkg.wake_alarm._alarm._beep_soft") as mock_soft,
        ):
            _play_tone(440)
            mock_soft.assert_called_once()


class TestWarnIfNoRealSink:
    """Tests for _warn_if_no_real_sink."""

    def test_logs_when_pactl_missing(self) -> None:
        """No pactl on PATH → warns and returns."""
        with (
            patch(
                "python_pkg.wake_alarm._alarm.shutil.which",
                return_value=None,
            ),
            patch(
                "python_pkg.wake_alarm._alarm.subprocess.run",
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
                "python_pkg.wake_alarm._alarm.shutil.which",
                return_value="/usr/bin/pactl",
            ),
            patch(
                "python_pkg.wake_alarm._alarm.subprocess.run",
                return_value=result,
            ),
            patch("python_pkg.wake_alarm._alarm._logger") as mock_log,
        ):
            _warn_if_no_real_sink()
            mock_log.warning.assert_called()

    def test_info_when_real_sink_present(self) -> None:
        """A non-auto_null sink → info log, no warning."""
        result = MagicMock()
        result.stdout = b"1\talsa_output.pci-0000_01_00.1.hdmi-stereo\tPipeWire\t-\t-\n"
        with (
            patch(
                "python_pkg.wake_alarm._alarm.shutil.which",
                return_value="/usr/bin/pactl",
            ),
            patch(
                "python_pkg.wake_alarm._alarm.subprocess.run",
                return_value=result,
            ),
            patch("python_pkg.wake_alarm._alarm._logger") as mock_log,
        ):
            _warn_if_no_real_sink()
            mock_log.info.assert_called()
            mock_log.warning.assert_not_called()

    def test_handles_pactl_failure(self) -> None:
        """OSError/TimeoutExpired running pactl → warning, no raise."""
        with (
            patch(
                "python_pkg.wake_alarm._alarm.shutil.which",
                return_value="/usr/bin/pactl",
            ),
            patch(
                "python_pkg.wake_alarm._alarm.subprocess.run",
                side_effect=subprocess.TimeoutExpired("pactl", 5),
            ),
        ):
            _warn_if_no_real_sink()  # must not raise


class TestMaxSinkVolume:
    """Tests for _max_sink_volume and _restore_sink_volume."""

    def test_returns_none_when_pactl_missing(self) -> None:
        """No pactl on PATH → returns None, logs warning."""
        with patch("python_pkg.wake_alarm._alarm.shutil.which", return_value=None):
            assert _max_sink_volume() is None

    def test_returns_none_when_default_sink_empty(self) -> None:
        """Empty get-default-sink output → returns None."""
        sink_proc = MagicMock(stdout=b"")
        with (
            patch(
                "python_pkg.wake_alarm._alarm.shutil.which",
                return_value="/usr/bin/pactl",
            ),
            patch(
                "python_pkg.wake_alarm._alarm.subprocess.run",
                return_value=sink_proc,
            ),
        ):
            assert _max_sink_volume() is None

    def test_query_failure_returns_none(self) -> None:
        """OSError during query → returns None, no raise."""
        with (
            patch(
                "python_pkg.wake_alarm._alarm.shutil.which",
                return_value="/usr/bin/pactl",
            ),
            patch(
                "python_pkg.wake_alarm._alarm.subprocess.run",
                side_effect=OSError("boom"),
            ),
        ):
            assert _max_sink_volume() is None

    def test_set_failure_returns_none(self) -> None:
        """OSError during set-sink-volume → returns None."""
        sink_proc = MagicMock(stdout=b"my_sink\n")
        vol_proc = MagicMock(stdout=b"Volume: front-left: 20641 / 31% / -30.10 dB")
        mute_proc = MagicMock(stdout=b"Mute: no\n")

        def fake_run(cmd: list[str], **_kwargs: object) -> MagicMock:
            if "get-default-sink" in cmd:
                return sink_proc
            if "get-sink-volume" in cmd:
                return vol_proc
            if "get-sink-mute" in cmd:
                return mute_proc
            raise subprocess.TimeoutExpired(cmd, 3)

        with (
            patch(
                "python_pkg.wake_alarm._alarm.shutil.which",
                return_value="/usr/bin/pactl",
            ),
            patch(
                "python_pkg.wake_alarm._alarm.subprocess.run",
                side_effect=fake_run,
            ),
        ):
            assert _max_sink_volume() is None

    def test_happy_path_returns_state(self) -> None:
        """Successful query+set returns the captured state tuple."""
        sink_proc = MagicMock(stdout=b"my_sink\n")
        vol_proc = MagicMock(stdout=b"Volume: front-left: 20641 / 31% / -30.10 dB")
        mute_proc = MagicMock(stdout=b"Mute: yes\n")
        ok = MagicMock(stdout=b"", returncode=0)

        def fake_run(cmd: list[str], **_kwargs: object) -> MagicMock:
            if "get-default-sink" in cmd:
                return sink_proc
            if "get-sink-volume" in cmd:
                return vol_proc
            if "get-sink-mute" in cmd:
                return mute_proc
            return ok

        with (
            patch(
                "python_pkg.wake_alarm._alarm.shutil.which",
                return_value="/usr/bin/pactl",
            ),
            patch(
                "python_pkg.wake_alarm._alarm.subprocess.run",
                side_effect=fake_run,
            ),
        ):
            state = _max_sink_volume()
        assert state == ("my_sink", "31%", True)

    def test_happy_path_no_percent_token(self) -> None:
        """Missing % token → falls back to 100%, not None."""
        sink_proc = MagicMock(stdout=b"s\n")
        vol_proc = MagicMock(stdout=b"weird output")
        mute_proc = MagicMock(stdout=b"Mute: no\n")
        ok = MagicMock(stdout=b"", returncode=0)

        def fake_run(cmd: list[str], **_kwargs: object) -> MagicMock:
            if "get-default-sink" in cmd:
                return sink_proc
            if "get-sink-volume" in cmd:
                return vol_proc
            if "get-sink-mute" in cmd:
                return mute_proc
            return ok

        with (
            patch(
                "python_pkg.wake_alarm._alarm.shutil.which",
                return_value="/usr/bin/pactl",
            ),
            patch(
                "python_pkg.wake_alarm._alarm.subprocess.run",
                side_effect=fake_run,
            ),
        ):
            state = _max_sink_volume()
        assert state == ("s", "100%", False)


class TestRestoreSinkVolume:
    """Tests for _restore_sink_volume."""

    def test_none_state_is_noop(self) -> None:
        """None state → does nothing, no pactl call."""
        with patch("python_pkg.wake_alarm._alarm.shutil.which") as mock_which:
            _restore_sink_volume(None)
            mock_which.assert_not_called()

    def test_no_pactl_returns_silently(self) -> None:
        """State present but pactl missing → no raise, no call."""
        with (
            patch("python_pkg.wake_alarm._alarm.shutil.which", return_value=None),
            patch("python_pkg.wake_alarm._alarm.subprocess.run") as mock_run,
        ):
            _restore_sink_volume(("sink", "42%", False))
            mock_run.assert_not_called()

    def test_restores_volume_and_mute(self) -> None:
        """Calls set-sink-volume and set-sink-mute with captured values."""
        with (
            patch(
                "python_pkg.wake_alarm._alarm.shutil.which",
                return_value="/usr/bin/pactl",
            ),
            patch("python_pkg.wake_alarm._alarm.subprocess.run") as mock_run,
        ):
            _restore_sink_volume(("sink", "42%", True))
        cmds = [call.args[0] for call in mock_run.call_args_list]
        assert ["/usr/bin/pactl", "set-sink-volume", "sink", "42%"] in cmds
        assert ["/usr/bin/pactl", "set-sink-mute", "sink", "1"] in cmds

    def test_oserror_during_restore_is_swallowed(self) -> None:
        """OSError during restore → no raise."""
        with (
            patch(
                "python_pkg.wake_alarm._alarm.shutil.which",
                return_value="/usr/bin/pactl",
            ),
            patch(
                "python_pkg.wake_alarm._alarm.subprocess.run",
                side_effect=OSError("boom"),
            ),
        ):
            _restore_sink_volume(("sink", "50%", False))  # must not raise


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
