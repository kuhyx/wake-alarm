"""Tests for _alarm_display.py — DDC/CI and DPMS display power helpers."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from python_pkg.wake_alarm._alarm_display import (
    _ddcutil_power_on,
    _restore_display,
    _wake_display,
)


class TestDdcutilPowerOn:
    """Tests for _ddcutil_power_on."""

    def test_skips_when_ddcutil_missing(self) -> None:
        """_ddcutil_power_on does nothing when ddcutil is not on PATH."""
        with (
            patch(
                "python_pkg.wake_alarm._alarm_display.shutil.which",
                return_value=None,
            ),
            patch("python_pkg.wake_alarm._alarm_display.subprocess.run") as mock_run,
        ):
            _ddcutil_power_on()
        mock_run.assert_not_called()

    def test_runs_setvcp_when_ddcutil_present(self) -> None:
        """_ddcutil_power_on sends setvcp D6 01 when ddcutil is found."""
        with (
            patch(
                "python_pkg.wake_alarm._alarm_display.shutil.which",
                return_value="/usr/bin/ddcutil",
            ),
            patch("python_pkg.wake_alarm._alarm_display.subprocess.run") as mock_run,
        ):
            _ddcutil_power_on()
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd == ["/usr/bin/ddcutil", "setvcp", "D6", "01"]

    def test_logs_success_when_returncode_zero(self) -> None:
        """_ddcutil_power_on logs success when setvcp returns 0."""
        with (
            patch(
                "python_pkg.wake_alarm._alarm_display.shutil.which",
                return_value="/usr/bin/ddcutil",
            ),
            patch(
                "python_pkg.wake_alarm._alarm_display.subprocess.run",
                return_value=MagicMock(returncode=0),
            ),
        ):
            _ddcutil_power_on()

    def test_handles_timeout(self) -> None:
        """_ddcutil_power_on does not raise on TimeoutExpired."""
        with (
            patch(
                "python_pkg.wake_alarm._alarm_display.shutil.which",
                return_value="/usr/bin/ddcutil",
            ),
            patch(
                "python_pkg.wake_alarm._alarm_display.subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd="ddcutil", timeout=10),
            ),
        ):
            _ddcutil_power_on()  # must not raise

    def test_handles_oserror(self) -> None:
        """_ddcutil_power_on does not raise on OSError."""
        with (
            patch(
                "python_pkg.wake_alarm._alarm_display.shutil.which",
                return_value="/usr/bin/ddcutil",
            ),
            patch(
                "python_pkg.wake_alarm._alarm_display.subprocess.run",
                side_effect=OSError("no device"),
            ),
        ):
            _ddcutil_power_on()  # must not raise


class TestDisplayHelpers:
    """Tests for _wake_display and _restore_display when xset is absent."""

    def test_wake_display_skips_when_xset_missing(self) -> None:
        """_wake_display skips xset commands but still attempts ddcutil."""
        with (
            patch(
                "python_pkg.wake_alarm._alarm_display.shutil.which",
                return_value=None,
            ),
            patch("python_pkg.wake_alarm._alarm_display.subprocess.run") as mock_run,
        ):
            _wake_display()
        mock_run.assert_not_called()

    def test_wake_display_runs_ddcutil_and_xset_commands(self) -> None:
        """_wake_display runs ddcutil setvcp, xset dpms force on, xset s off."""
        with (
            patch(
                "python_pkg.wake_alarm._alarm_display.shutil.which",
                return_value="/usr/bin/xset",
            ),
            patch("python_pkg.wake_alarm._alarm_display.subprocess.run") as mock_run,
        ):
            _wake_display()
        # 1 ddcutil setvcp call + 2 xset calls
        assert mock_run.call_count == 3
        call_args = [call[0][0] for call in mock_run.call_args_list]
        assert ["/usr/bin/xset", "setvcp", "D6", "01"] in call_args
        assert ["/usr/bin/xset", "dpms", "force", "on"] in call_args
        assert ["/usr/bin/xset", "s", "off"] in call_args

    def test_restore_display_skips_when_xset_missing(self) -> None:
        """_restore_display does nothing when xset is not on PATH."""
        with (
            patch(
                "python_pkg.wake_alarm._alarm_display.shutil.which",
                return_value=None,
            ),
            patch("python_pkg.wake_alarm._alarm_display.subprocess.run") as mock_run,
        ):
            _restore_display()
        mock_run.assert_not_called()
