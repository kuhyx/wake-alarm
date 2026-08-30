"""Tests for _trigger.py — the systemd invocation and the CLI entry point.

Split from ``test_trigger.py`` for the 250-line cap. The header is copied
wholesale rather than trimmed: without the autouse ``_ungated`` fixture these
tests read the *real* gates on the host and would pass or fail by accident.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from wake_alarm._sync import Alarm
from wake_alarm._trigger import (
    _parse_args,
    _start_target_unit,
    main,
)


def _at(hour: int, minute: int) -> datetime:
    """Return a Sunday at the given local wall-clock time, timezone-aware.

    Built the same way production does — naive wall clock, then astimezone()
    to attach the system offset — so the tests exercise the real comparison
    semantics rather than a hand-picked fixed offset.
    """
    return datetime(2026, 7, 19, hour, minute, tzinfo=None).astimezone()


@pytest.fixture(autouse=True)
def _ungated() -> None:
    """Open every gate unless a test closes one.

    The once-per-day latch is stubbed: unstubbed it reads the *real*
    session record on the host, so a test run started while an alarm was
    actually ringing would silently invert half these assertions.
    """
    with (
        patch("wake_alarm._trigger.was_trigger_fired_today", return_value=False),
    ):
        yield


class TestStartTargetUnit:
    """Tests for the systemctl invocation."""

    def test_starts_the_orchestrator_not_the_alarm(self) -> None:
        """The trigger must start morning-routine, never wake-alarm."""
        completed = MagicMock(returncode=0)
        with patch("subprocess.run", return_value=completed) as run:
            assert _start_target_unit()
        assert run.call_args[0][0] == [
            "systemctl",
            "--user",
            "start",
            "morning-routine.service",
        ]

    def test_nonzero_exit_is_reported(self) -> None:
        """A systemctl failure returns False rather than raising."""
        completed = MagicMock(returncode=1, stderr=b"no such unit")
        with patch("subprocess.run", return_value=completed):
            assert not _start_target_unit()

    def test_missing_systemctl_is_swallowed(self) -> None:
        """An OSError (no systemctl) returns False rather than raising."""
        with patch("subprocess.run", side_effect=OSError("not found")):
            assert not _start_target_unit()

    def test_does_not_raise_on_failure(self) -> None:
        """check=False: a failing start never raises CalledProcessError."""
        completed = MagicMock(returncode=1, stderr=b"")
        with patch("subprocess.run", return_value=completed) as run:
            _start_target_unit()
        assert run.call_args.kwargs["check"] is False


class TestMain:
    """Tests for the tick entry point."""

    def test_parse_args_default(self) -> None:
        """--dry-run defaults to off."""
        assert not _parse_args([]).dry_run

    def _run_main(self, argv: list[str], now: datetime, alarm: Alarm) -> MagicMock:
        with (
            patch("sys.argv", ["_trigger", *argv]),
            patch("wake_alarm._trigger._now", return_value=now),
            patch("wake_alarm._trigger.get_alarm", return_value=alarm),
            patch("wake_alarm._trigger._start_target_unit") as start,
        ):
            main()
        return start

    def test_a_successful_start_latches_the_day(self) -> None:
        """Firing records the latch, so later ticks in the window skip.

        Without this the routine is restarted on every tick for the rest of
        ``TRIGGER_CATCHUP_MINUTES``: the unit is Type=simple, so a start while
        it runs is a no-op, but the moment the workout lock finishes the next
        tick relaunches it on top of the user.
        """
        with (
            patch("sys.argv", ["_trigger"]),
            patch("wake_alarm._trigger._now", return_value=_at(6, 45)),
            patch(
                "wake_alarm._trigger.get_alarm",
                return_value=Alarm(6, 45, "remote"),
            ),
            patch("wake_alarm._trigger._start_target_unit", return_value=True),
            patch("wake_alarm._trigger.save_trigger_fired") as saved,
        ):
            main()
        assert saved.call_count == 1
        assert saved.call_args.kwargs["fired_at"] == _at(6, 45).isoformat()

    def test_a_failed_start_does_not_latch(self) -> None:
        """A start that failed must stay retryable on the next tick."""
        with (
            patch("sys.argv", ["_trigger"]),
            patch("wake_alarm._trigger._now", return_value=_at(6, 45)),
            patch(
                "wake_alarm._trigger.get_alarm",
                return_value=Alarm(6, 45, "remote"),
            ),
            patch("wake_alarm._trigger._start_target_unit", return_value=False),
            patch("wake_alarm._trigger.save_trigger_fired") as saved,
        ):
            main()
        saved.assert_not_called()

    def test_fires_at_the_alarm_minute(self) -> None:
        """On the alarm minute the target unit is started."""
        start = self._run_main([], _at(6, 45), Alarm(6, 45, "remote"))
        start.assert_called_once()

    def test_does_not_fire_early(self) -> None:
        """Before the alarm nothing is started."""
        start = self._run_main([], _at(5, 0), Alarm(6, 45, "remote"))
        start.assert_not_called()

    def test_dry_run_never_starts_anything(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """--dry-run reports WOULD FIRE without touching systemd."""
        start = self._run_main(["--dry-run"], _at(6, 45), Alarm(6, 45, "remote"))
        start.assert_not_called()
        assert "WOULD FIRE" in capsys.readouterr().out

    def test_dry_run_reports_not_firing(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """--dry-run explains why it is not firing."""
        self._run_main(["--dry-run"], _at(5, 0), Alarm(6, 45, "remote"))
        out = capsys.readouterr().out
        assert "not firing" in out
        assert "still ahead" in out

    @pytest.mark.parametrize("source", ["fallback", "stale-cache"])
    def test_warns_when_firing_on_a_degraded_source(
        self, caplog: pytest.LogCaptureFixture, source: str
    ) -> None:
        """Firing on a non-phone alarm time is logged loudly."""
        with caplog.at_level("WARNING"):
            self._run_main([], _at(6, 45), Alarm(6, 45, source))
        assert "degraded alarm source" in caplog.text

    @pytest.mark.parametrize("source", ["remote", "cache"])
    def test_quiet_when_firing_on_the_phone_alarm(
        self, caplog: pytest.LogCaptureFixture, source: str
    ) -> None:
        """A normal fire does not emit the degraded-source warning."""
        with caplog.at_level("WARNING"):
            self._run_main([], _at(6, 45), Alarm(6, 45, source))
        assert "degraded alarm source" not in caplog.text
