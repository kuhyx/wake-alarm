"""Tests for raising every monitor to full brightness."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from wake_alarm._brightness import _set_max_brightness


class TestSetMaxBrightness:
    """Tests for _set_max_brightness."""

    def test_noop_when_xrandr_missing(self) -> None:
        """No xrandr on PATH → subprocess.run never called."""
        with (
            patch("wake_alarm._audio.shutil.which", return_value=None),
            patch("wake_alarm._audio.subprocess.run") as mock_run,
        ):
            _set_max_brightness()
            mock_run.assert_not_called()

    def test_noop_on_oserror_from_query(self) -> None:
        """OSError from xrandr --query is suppressed."""
        with (
            patch(
                "wake_alarm._audio.shutil.which",
                return_value="/usr/bin/xrandr",
            ),
            patch(
                "wake_alarm._audio.subprocess.run",
                side_effect=OSError("no display"),
            ),
        ):
            _set_max_brightness()  # must not raise

    def test_noop_on_timeout_from_query(self) -> None:
        """TimeoutExpired from xrandr --query is suppressed."""
        with (
            patch(
                "wake_alarm._audio.shutil.which",
                return_value="/usr/bin/xrandr",
            ),
            patch(
                "wake_alarm._audio.subprocess.run",
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
                "wake_alarm._audio.shutil.which",
                return_value="/usr/bin/xrandr",
            ),
            patch("wake_alarm._audio.subprocess.run", side_effect=fake_run),
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
                "wake_alarm._audio.shutil.which",
                return_value="/usr/bin/xrandr",
            ),
            patch(
                "wake_alarm._audio.subprocess.run",
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
                "wake_alarm._audio.shutil.which",
                return_value="/usr/bin/xrandr",
            ),
            patch(
                "wake_alarm._audio.subprocess.run",
                side_effect=_run_side_effect,
            ),
        ):
            _set_max_brightness()  # must not raise
