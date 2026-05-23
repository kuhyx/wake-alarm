"""Tests for _alarm.py — wake alarm daemon, UI, and beep logic."""

from __future__ import annotations

import pathlib
import subprocess
import tkinter as tk
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

if TYPE_CHECKING:
    from collections.abc import Generator

from python_pkg.wake_alarm._alarm import (
    _beep_loud,
    _beep_medium,
    _beep_soft,
    _find_fan_hwmon,
    _generate_code,
    _is_alarm_day,
    _max_fans,
    _play_on_extra_devices,
    _restore_display,
    _restore_fans,
    _set_max_brightness,
    _should_run_alarm,
    _speaker_test_path,
    _wake_display,
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

    def test_beep_medium_calls_speaker_test(self) -> None:
        """_beep_medium runs speaker-test subprocess."""
        with (
            patch(
                "python_pkg.wake_alarm._alarm._speaker_test_path",
                return_value="/usr/bin/speaker-test",
            ),
            patch(
                "python_pkg.wake_alarm._alarm.subprocess.run",
            ) as mock_run,
        ):
            _beep_medium(frequency=800)
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert "/usr/bin/speaker-test" in args
            assert "800" in args

    def test_beep_medium_falls_back_on_error(self) -> None:
        """_beep_medium falls back to soft beep on OSError."""
        with (
            patch(
                "python_pkg.wake_alarm._alarm._speaker_test_path",
                return_value="/usr/bin/speaker-test",
            ),
            patch(
                "python_pkg.wake_alarm._alarm.subprocess.run",
                side_effect=OSError("no speaker-test"),
            ),
            patch(
                "python_pkg.wake_alarm._alarm._beep_soft",
            ) as mock_soft,
        ):
            _beep_medium()
            mock_soft.assert_called_once()

    def test_beep_medium_falls_back_on_timeout(self) -> None:
        """_beep_medium falls back on TimeoutExpired."""
        from subprocess import TimeoutExpired

        with (
            patch(
                "python_pkg.wake_alarm._alarm._speaker_test_path",
                return_value="/usr/bin/speaker-test",
            ),
            patch(
                "python_pkg.wake_alarm._alarm.subprocess.run",
                side_effect=TimeoutExpired("cmd", 3),
            ),
            patch(
                "python_pkg.wake_alarm._alarm._beep_soft",
            ) as mock_soft,
        ):
            _beep_medium()
            mock_soft.assert_called_once()

    def test_beep_medium_falls_back_on_missing_binary(self) -> None:
        """_beep_medium falls back when speaker-test binary not found."""
        with (
            patch(
                "python_pkg.wake_alarm._alarm._speaker_test_path",
                side_effect=FileNotFoundError("not found"),
            ),
            patch(
                "python_pkg.wake_alarm._alarm._beep_soft",
            ) as mock_soft,
        ):
            _beep_medium()
            mock_soft.assert_called_once()

    def test_beep_loud_calls_speaker_test(self) -> None:
        """_beep_loud runs speaker-test subprocess."""
        with (
            patch(
                "python_pkg.wake_alarm._alarm._speaker_test_path",
                return_value="/usr/bin/speaker-test",
            ),
            patch(
                "python_pkg.wake_alarm._alarm.subprocess.run",
            ) as mock_run,
        ):
            _beep_loud(frequency=1200)
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert "1200" in args

    def test_beep_loud_falls_back_on_error(self) -> None:
        """_beep_loud falls back to soft beep on OSError."""
        with (
            patch(
                "python_pkg.wake_alarm._alarm._speaker_test_path",
                return_value="/usr/bin/speaker-test",
            ),
            patch(
                "python_pkg.wake_alarm._alarm.subprocess.run",
                side_effect=OSError("fail"),
            ),
            patch(
                "python_pkg.wake_alarm._alarm._beep_soft",
            ) as mock_soft,
        ):
            _beep_loud()
            mock_soft.assert_called_once()

    def test_beep_loud_falls_back_on_missing_binary(self) -> None:
        """_beep_loud falls back when speaker-test binary not found."""
        with (
            patch(
                "python_pkg.wake_alarm._alarm._speaker_test_path",
                side_effect=FileNotFoundError("not found"),
            ),
            patch(
                "python_pkg.wake_alarm._alarm._beep_soft",
            ) as mock_soft,
        ):
            _beep_loud()
            mock_soft.assert_called_once()


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

    def test_returns_none_when_no_hwmon(self) -> None:
        """No fan controller → returns None immediately."""
        with patch("python_pkg.wake_alarm._alarm._find_fan_hwmon", return_value=None):
            assert _max_fans() is None

    def test_returns_none_on_oserror_reading_pwm(self, tmp_path: pathlib.Path) -> None:
        """Missing pwm files → returns None."""
        hwmon_dir = str(tmp_path)
        with patch(
            "python_pkg.wake_alarm._alarm._find_fan_hwmon", return_value=hwmon_dir
        ):
            assert _max_fans() is None

    def test_returns_none_on_script_oserror(self, tmp_path: pathlib.Path) -> None:
        """OSError running fan script → returns None."""
        (tmp_path / "pwm1_enable").write_text("5\n")
        (tmp_path / "pwm1").write_text("165\n")
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
            assert _max_fans() is None

    def test_returns_none_on_script_timeout(self, tmp_path: pathlib.Path) -> None:
        """TimeoutExpired running fan script → returns None."""
        (tmp_path / "pwm1_enable").write_text("5\n")
        (tmp_path / "pwm1").write_text("165\n")
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
            assert _max_fans() is None

    def test_returns_none_on_nonzero_returncode(self, tmp_path: pathlib.Path) -> None:
        """Fan script exits non-zero → returns None."""
        (tmp_path / "pwm1_enable").write_text("5\n")
        (tmp_path / "pwm1").write_text("165\n")
        mock_result = MagicMock()
        mock_result.returncode = 1
        with (
            patch(
                "python_pkg.wake_alarm._alarm._find_fan_hwmon",
                return_value=str(tmp_path),
            ),
            patch(
                "python_pkg.wake_alarm._alarm.subprocess.run", return_value=mock_result
            ),
        ):
            assert _max_fans() is None

    def test_returns_state_on_success(self, tmp_path: pathlib.Path) -> None:
        """Successful run → returns (hwmon, old_enable, old_pwm)."""
        (tmp_path / "pwm1_enable").write_text("5\n")
        (tmp_path / "pwm1").write_text("165\n")
        mock_result = MagicMock()
        mock_result.returncode = 0
        with (
            patch(
                "python_pkg.wake_alarm._alarm._find_fan_hwmon",
                return_value=str(tmp_path),
            ),
            patch(
                "python_pkg.wake_alarm._alarm.subprocess.run", return_value=mock_result
            ),
        ):
            result = _max_fans()
        assert result == (str(tmp_path), "5", "165")


class TestRestoreFans:
    """Tests for _restore_fans."""

    def test_noop_when_state_is_none(self) -> None:
        """None state → subprocess.run is never called."""
        with patch("python_pkg.wake_alarm._alarm.subprocess.run") as mock_run:
            _restore_fans(None)
            mock_run.assert_not_called()

    def test_calls_fan_script_with_saved_values(self) -> None:
        """Saved state → fan script called with restore + old values."""
        with patch("python_pkg.wake_alarm._alarm.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            _restore_fans(("/sys/class/hwmon/hwmon6", "5", "165"))
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert "restore" in args
            assert "5" in args
            assert "165" in args

    def test_ignores_oserror_on_restore(self) -> None:
        """OSError from fan script is silently suppressed."""
        with patch(
            "python_pkg.wake_alarm._alarm.subprocess.run",
            side_effect=OSError("no script"),
        ):
            _restore_fans(("/sys/class/hwmon/hwmon6", "5", "165"))  # must not raise

    def test_ignores_timeout_on_restore(self) -> None:
        """TimeoutExpired from fan script is silently suppressed."""
        with patch(
            "python_pkg.wake_alarm._alarm.subprocess.run",
            side_effect=subprocess.TimeoutExpired("fan", 5),
        ):
            _restore_fans(("/sys/class/hwmon/hwmon6", "5", "165"))  # must not raise


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
