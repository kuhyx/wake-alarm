"""RTC arming: which morning, whether to arm, and never on this host."""

from __future__ import annotations

from datetime import date, datetime
import logging
import subprocess
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from wake_alarm import _rtc, _rtc_hw
from wake_alarm._rtc import Plan, apply, describe, main, plan
from wake_alarm._rtc_hw import ArmedRecord, read_record
from wake_alarm._sync import Alarm

if TYPE_CHECKING:
    from collections.abc import Generator

REAL_NOW = _rtc._now
ALARM = Alarm(7, 0, "cache")
MONDAY_EVENING = datetime(2026, 10, 5, 22, 0).astimezone()


def _done(code: int = 0, err: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], code, stdout="", stderr=err)


@pytest.fixture(autouse=True)
def _alarm() -> Generator[None]:
    with patch.object(_rtc, "get_alarm", return_value=ALARM):
        yield


class TestPlan:
    def test_evening_targets_tomorrow_minus_the_lead(self) -> None:
        chosen = plan(MONDAY_EVENING, ALARM)
        assert chosen.target == date(2026, 10, 6)
        assert chosen.wake_at == datetime(2026, 10, 6, 6, 50).astimezone()
        assert chosen.arm

    def test_small_hours_target_the_same_morning(self) -> None:
        chosen = plan(datetime(2026, 10, 6, 2, 0).astimezone(), ALARM)
        assert chosen.target == date(2026, 10, 6)

    def test_past_the_wake_instant_targets_tomorrow(self) -> None:
        chosen = plan(datetime(2026, 10, 6, 6, 50).astimezone(), ALARM)
        assert chosen.target == date(2026, 10, 7)

    def test_a_later_alarm_is_clamped_to_eight(self) -> None:
        chosen = plan(MONDAY_EVENING, Alarm(13, 0, "cache"))
        assert chosen.wake_at.hour == 7
        assert chosen.wake_at.minute == 50

    def test_carrot_days_are_skipped(self) -> None:
        chosen = plan(datetime(2026, 10, 1, 22, 0).astimezone(), ALARM)  # -> Fri
        assert not chosen.arm
        assert chosen.reason == "Fri is not a stick day"

    def test_free_days_are_skipped(self) -> None:
        with patch.object(_rtc.freedays, "is_free_day", return_value=True):
            chosen = plan(MONDAY_EVENING, ALARM)
        assert (chosen.arm, chosen.reason) == (False, "free day")


class TestApply:
    def test_armed_is_logged_once(self, caplog: pytest.LogCaptureFixture) -> None:
        chosen = plan(MONDAY_EVENING, ALARM)
        with (
            patch.object(_rtc_hw, "_run", return_value=_done()),
            caplog.at_level(logging.INFO),
        ):
            assert apply(chosen)
            assert apply(chosen)
        assert caplog.text.count("rtc_armed:") == 1
        assert "target_date" in str(caplog.records[-1].__dict__.get("fields"))

    def test_skip_and_failure(self, caplog: pytest.LogCaptureFixture) -> None:
        skip = Plan(date(2026, 10, 2), MONDAY_EVENING, arm=False, reason="free day")
        with caplog.at_level(logging.INFO):
            assert not apply(skip)
            with patch.object(_rtc_hw, "_run", return_value=_done(1, "denied")):
                assert not apply(plan(MONDAY_EVENING, ALARM))
        assert "rtc_skip: free day" in caplog.text
        assert "rtcwake failed: denied" in caplog.text


class TestDisarm:
    """A skipped morning clears the alarm we armed -- and only ours."""

    skip = Plan(date(2026, 10, 2), MONDAY_EVENING, arm=False, reason="free day")

    def _arm_ours(self) -> int:
        chosen = plan(MONDAY_EVENING, ALARM)
        with patch.object(_rtc_hw, "_run", return_value=_done()):
            assert apply(chosen)
        _rtc_hw.WAKEALARM_FILE.write_text(str(chosen.epoch))
        return chosen.epoch

    def test_ours_is_disarmed_and_logged(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        epoch = self._arm_ours()
        run = MagicMock(return_value=_done())
        with patch.object(_rtc_hw, "_run", run), caplog.at_level(logging.INFO):
            assert not apply(self.skip)
        assert run.call_args.args[0] == [
            "sudo",
            "-n",
            "/usr/sbin/rtcwake",
            "-m",
            "disable",
        ]
        assert "rtc_disarmed: cleared 2026-10-06 (free day)" in caplog.text
        assert read_record() is None
        assert epoch

    def test_someone_elses_alarm_is_left_alone(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        self._arm_ours()
        _rtc_hw.WAKEALARM_FILE.write_text("1234")
        with caplog.at_level(logging.INFO):
            apply(self.skip)  # the conftest seam would raise on any rtcwake
        assert "rtc_disarmed" not in caplog.text
        assert read_record() is None

    def test_nothing_of_ours_means_no_rtcwake(self) -> None:
        _rtc_hw.WAKEALARM_FILE.write_text("1234")
        assert not apply(self.skip)

    def test_a_failed_disarm_keeps_the_record(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        self._arm_ours()
        with (
            patch.object(_rtc_hw, "_run", return_value=_done(1, "denied")),
            caplog.at_level(logging.INFO),
        ):
            apply(self.skip)
        assert "rtcwake -m disable failed: denied" in caplog.text
        assert read_record() is not None

    def test_dry_run_says_what_it_would_disarm(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        epoch = self._arm_ours()
        assert main(["--dry-run", "--at", "2026-10-08T22:00:00"]) == 0  # -> Fri
        assert f"would disarm ours: {epoch} for 2026-10-06" in capsys.readouterr().out
        _rtc_hw.WAKEALARM_FILE.write_text("1")
        assert main(["--dry-run", "--at", "2026-10-08T22:00:00"]) == 0
        assert "would disarm" not in capsys.readouterr().out
        assert read_record() == ArmedRecord(epoch, "2026-10-06")


class TestCli:
    def test_dry_run_and_show(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert main(["--dry-run", "--at", "2026-10-05T22:00:00"]) == 0
        assert capsys.readouterr().out.startswith("ARM 2026-10-06")
        epoch = plan(MONDAY_EVENING, ALARM).epoch
        _rtc_hw.WAKEALARM_FILE.write_text(str(epoch))
        assert main(["--show"]) == 0
        out = capsys.readouterr().out
        expected = datetime(2026, 10, 6, 6, 50).astimezone().isoformat()
        assert f"rtc wakealarm: {expected}" in out
        assert "mode: hibernate" in out
        assert "armed by us: none" in out
        _rtc_hw.WAKEALARM_FILE.unlink()
        assert main(["--show"]) == 0
        assert "rtc wakealarm: none" in capsys.readouterr().out

    def test_at_needs_dry_run(self) -> None:
        with pytest.raises(SystemExit):
            main(["--arm", "--at", "2026-10-05T22:00:00"])

    def test_arm_exit_codes(self) -> None:
        with (
            patch.object(_rtc, "configure_logging"),
            patch.object(_rtc, "_now", return_value=MONDAY_EVENING),
        ):
            with patch.object(_rtc_hw, "_run", return_value=_done()):
                assert main(["--arm"]) == 0
            _rtc_hw.WAKEALARM_FILE.write_text("1")
            with patch.object(_rtc_hw, "_run", return_value=_done(1)):
                assert main(["--arm"]) == 1
        with (
            patch.object(_rtc, "configure_logging"),
            patch.object(
                _rtc, "_now", return_value=datetime(2026, 10, 1, 22).astimezone()
            ),
            patch("sys.argv", ["prog", "--arm"]),
        ):
            assert main() == 0  # a skip is not a failure

    def test_describe(self) -> None:
        assert "skip" in describe(
            Plan(date(2026, 10, 2), MONDAY_EVENING, arm=False, reason="x")
        )


def test_real_now_is_aware() -> None:
    assert REAL_NOW().tzinfo is not None
