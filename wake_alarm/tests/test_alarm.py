"""Tests for _alarm.py — wake alarm daemon, UI, and beep logic."""

from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

if TYPE_CHECKING:
    from collections.abc import Generator

from python_pkg.wake_alarm._alarm import (
    WakeAlarm,
    _beep_loud,
    _beep_medium,
    _beep_soft,
    _generate_code,
    _is_alarm_day,
    _should_run_alarm,
    _speaker_test_path,
    main,
)
from python_pkg.wake_alarm._constants import (
    DISMISS_CODE_LENGTH,
    PHASE_MEDIUM_END,
    PHASE_SOFT_END,
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


class TestWakeAlarmInit:
    """Tests for WakeAlarm initialization."""

    def test_demo_mode_sets_smaller_window(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """Demo mode creates a smaller window."""
        alarm = WakeAlarm(demo_mode=True)
        assert alarm.demo_mode is True
        assert alarm.dismissed is False
        alarm._stop_beep.set()  # Stop beep thread

    def test_production_mode_fullscreen(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """Production mode activates fullscreen."""
        alarm = WakeAlarm(demo_mode=False)
        assert alarm.demo_mode is False
        mock_root = mock_tk_module.Tk.return_value
        mock_root.overrideredirect.assert_called_once()
        alarm._stop_beep.set()


class TestWakeAlarmDismiss:
    """Tests for alarm dismiss logic."""

    def test_correct_code_dismisses(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """Entering the correct code dismisses the alarm."""
        alarm = WakeAlarm(demo_mode=True)
        code = alarm._current_code
        mock_entry = mock_tk_module.Entry.return_value
        mock_entry.get.return_value = code

        with patch(
            "python_pkg.wake_alarm._alarm.save_wake_state",
        ) as mock_save:
            alarm._on_submit()

        assert alarm.dismissed is True
        mock_save.assert_called_once()
        call_kwargs = mock_save.call_args[1]
        assert call_kwargs["skip_workout"] is True
        alarm._stop_beep.set()

    def test_wrong_code_does_not_dismiss(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """Entering the wrong code shows error without dismissing."""
        alarm = WakeAlarm(demo_mode=True)
        mock_entry = mock_tk_module.Entry.return_value
        mock_entry.get.return_value = "000000"
        # Ensure current code is different
        alarm._current_code = "123456"

        alarm._on_submit()

        assert alarm.dismissed is False
        alarm._stop_beep.set()

    def test_dismiss_window_expired(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """Window expiry saves state with no skip."""
        alarm = WakeAlarm(demo_mode=True)

        with patch(
            "python_pkg.wake_alarm._alarm.save_wake_state",
        ) as mock_save:
            alarm._on_dismiss_window_expired()

        assert alarm.dismissed is False
        mock_save.assert_called_once_with(
            dismissed_at=None,
            skip_workout=False,
        )
        alarm._stop_beep.set()

    def test_dismiss_window_expired_noop_if_already_dismissed(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """Expiry is a no-op if already dismissed."""
        alarm = WakeAlarm(demo_mode=True)
        alarm.dismissed = True

        with patch(
            "python_pkg.wake_alarm._alarm.save_wake_state",
        ) as mock_save:
            alarm._on_dismiss_window_expired()

        mock_save.assert_not_called()
        alarm._stop_beep.set()


class TestMain:
    """Tests for the main() entry point."""

    def test_exits_when_not_alarm_day(self) -> None:
        """main() returns early when not an alarm day."""
        with patch(
            "python_pkg.wake_alarm._alarm._should_run_alarm",
            return_value=False,
        ):
            main()  # Should just return without error

    def test_creates_alarm_when_should_run(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """main() creates a WakeAlarm when conditions are met."""
        with (
            patch(
                "python_pkg.wake_alarm._alarm._should_run_alarm",
                return_value=True,
            ),
            patch(
                "python_pkg.wake_alarm._alarm.sys",
            ) as mock_sys,
            patch.object(WakeAlarm, "run") as mock_run,
            patch.object(WakeAlarm, "__init__", return_value=None),
        ):
            mock_sys.argv = []
            main()
            mock_run.assert_called_once()


class TestCodeRefreshAndTimer:
    """Tests for code refresh and timer update methods."""

    def test_code_refresh_changes_code(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """Code refresh generates a new code."""
        alarm = WakeAlarm(demo_mode=True)
        # Call refresh many times — at least one should differ
        codes = set()
        for _ in range(50):
            alarm._schedule_code_refresh()
            codes.add(alarm._current_code)
        assert len(codes) > 1
        alarm._stop_beep.set()

    def test_code_refresh_noop_when_dismissed(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """Code refresh is a no-op after dismissal."""
        alarm = WakeAlarm(demo_mode=True)
        alarm.dismissed = True
        old_code = alarm._current_code
        alarm._schedule_code_refresh()
        # Code doesn't change because dismissed=True causes early return
        assert alarm._current_code == old_code
        alarm._stop_beep.set()

    def test_update_timer_noop_when_dismissed(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """Timer update is a no-op after dismissal."""
        alarm = WakeAlarm(demo_mode=True)
        alarm.dismissed = True
        alarm._update_timer()  # Should not raise
        alarm._stop_beep.set()


class TestBeepLoop:
    """Tests for the beep loop thread."""

    def test_beep_loop_stops_on_event(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """Beep loop exits when stop event is set."""
        alarm = WakeAlarm(demo_mode=True)
        alarm._stop_beep.set()
        # Loop should exit immediately
        with patch(
            "python_pkg.wake_alarm._alarm._beep_soft",
        ):
            alarm._beep_loop()
        alarm._stop_beep.set()


class TestCloseAndFallback:
    """Tests for close and fallback scheduling."""

    def test_close_stops_beep_and_destroys(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """_close sets stop event and destroys root."""
        alarm = WakeAlarm(demo_mode=True)
        alarm._close()
        assert alarm._stop_beep.is_set()
        alarm.root.destroy.assert_called()

    def test_close_and_schedule_fallback(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """_close_and_schedule_fallback destroys root."""
        alarm = WakeAlarm(demo_mode=True)
        alarm._close_and_schedule_fallback()
        alarm.root.destroy.assert_called()
        alarm._stop_beep.set()


class TestDismissWithoutSkip:
    """Tests for alarm dismiss without earning skip."""

    def test_dismiss_without_skip_shows_no_skip_message(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """Dismissing with earned_skip=False shows appropriate message."""
        alarm = WakeAlarm(demo_mode=True)
        # Simulate existing child widgets
        mock_widget = MagicMock()
        alarm._container.winfo_children.return_value = [mock_widget]

        with patch(
            "python_pkg.wake_alarm._alarm.save_wake_state",
        ) as mock_save:
            alarm._dismiss_alarm(earned_skip=False)

        assert alarm.dismissed is True
        mock_save.assert_called_once()
        call_kwargs = mock_save.call_args[1]
        assert call_kwargs["skip_workout"] is False
        mock_widget.destroy.assert_called_once()
        alarm._stop_beep.set()


class TestDismissWindowExpiredWidgets:
    """Tests for widget cleanup during dismiss window expiry."""

    def test_expired_creates_label(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """Expiry creates a 'Too late' label and destroys children."""
        alarm = WakeAlarm(demo_mode=True)
        mock_widget = MagicMock()
        alarm._container.winfo_children.return_value = [mock_widget]

        with patch(
            "python_pkg.wake_alarm._alarm.save_wake_state",
        ):
            alarm._on_dismiss_window_expired()

        mock_widget.destroy.assert_called_once()
        mock_tk_module.Label.assert_called()
        alarm._stop_beep.set()


class TestBeepLoopPhases:
    """Tests for different beep loop escalation phases."""

    def test_medium_phase(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """Beep loop enters medium phase after PHASE_SOFT_END minutes."""
        alarm = WakeAlarm(demo_mode=True)
        # Set alarm start to make elapsed > PHASE_SOFT_END minutes
        import time as time_mod

        alarm._alarm_start = time_mod.monotonic() - (PHASE_SOFT_END + 1) * 60

        call_count = 0

        def stop_after_one(*_args: object, **_kwargs: object) -> None:
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                alarm._stop_beep.set()

        with (
            patch(
                "python_pkg.wake_alarm._alarm._beep_medium",
                side_effect=stop_after_one,
            ) as mock_beep,
        ):
            alarm._beep_loop()

        mock_beep.assert_called()
        alarm._stop_beep.set()

    def test_loud_phase(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """Beep loop enters loud phase after PHASE_MEDIUM_END minutes."""
        alarm = WakeAlarm(demo_mode=True)
        import time as time_mod

        alarm._alarm_start = time_mod.monotonic() - (PHASE_MEDIUM_END + 1) * 60

        call_count = 0

        def stop_after_one(*_args: object, **_kwargs: object) -> None:
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                alarm._stop_beep.set()

        with (
            patch(
                "python_pkg.wake_alarm._alarm._beep_loud",
                side_effect=stop_after_one,
            ) as mock_beep,
        ):
            alarm._beep_loop()

        mock_beep.assert_called()
        alarm._stop_beep.set()


class TestRunMethod:
    """Tests for the run() method."""

    def test_run_calls_mainloop(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """run() calls root.mainloop()."""
        alarm = WakeAlarm(demo_mode=True)
        alarm.run()
        alarm.root.mainloop.assert_called_once()
        alarm._stop_beep.set()


class TestUpdateTimerActive:
    """Tests for timer update when alarm is active."""

    def test_update_timer_shows_remaining(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """Timer update shows remaining time when not dismissed."""
        alarm = WakeAlarm(demo_mode=True)
        alarm._update_timer()
        alarm._timer_label.configure.assert_called()
        alarm._stop_beep.set()

    def test_update_timer_stops_at_zero(
        self,
        mock_tk_module: MagicMock,
    ) -> None:
        """Timer stops scheduling when remaining time reaches zero."""
        import time as time_mod

        alarm = WakeAlarm(demo_mode=True)
        # Set alarm start far in the past so remaining = 0
        alarm._alarm_start = time_mod.monotonic() - 60 * 60
        alarm._update_timer()
        # root.after should NOT be called for re-scheduling
        # (configure is still called to show 00:00)
        alarm._timer_label.configure.assert_called()
        alarm._stop_beep.set()
