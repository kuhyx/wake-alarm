"""The RTC alarm and our record of it, with sudo faked."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
from unittest.mock import MagicMock, patch

from wake_alarm import _rtc_hw
from wake_alarm._rtc_hw import (
    ArmedRecord,
    arm,
    current_alarm,
    disarm_ours,
    read_record,
)

# Bound at import, before conftest swaps the seam for a raiser.
REAL_RUN = _rtc_hw._run
EPOCH = 1791265560


def _done(code: int = 0, err: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], code, stdout="", stderr=err)


def test_reads_the_pending_alarm() -> None:
    assert current_alarm() is None
    _rtc_hw.WAKEALARM_FILE.write_text("\n")
    assert current_alarm() is None
    _rtc_hw.WAKEALARM_FILE.write_text(f"{EPOCH}\n")
    assert current_alarm() == EPOCH


def test_already_set_needs_no_sudo_but_is_recorded() -> None:
    _rtc_hw.WAKEALARM_FILE.write_text(str(EPOCH))
    assert arm(EPOCH, "2026-10-06") == (True, "already set")
    assert read_record() == ArmedRecord(EPOCH, "2026-10-06")


def test_arms_through_sudo_rtcwake() -> None:
    run = MagicMock(return_value=_done())
    with patch.object(_rtc_hw, "_run", run):
        assert arm(EPOCH, "2026-10-06") == (True, "armed")
    assert run.call_args.args[0] == [
        "sudo",
        "-n",
        "/usr/sbin/rtcwake",
        "-m",
        "no",
        "-t",
        str(EPOCH),
    ]
    assert read_record() == ArmedRecord(EPOCH, "2026-10-06")


def test_arm_failures_record_nothing() -> None:
    with patch.object(_rtc_hw, "_run", return_value=_done(1, "denied")):
        assert arm(EPOCH, "d") == (False, "denied")
    with patch.object(_rtc_hw, "_run", side_effect=OSError("no sudo")):
        assert arm(EPOCH, "d") == (False, "no sudo")
    assert read_record() is None


def test_disarm_only_ours() -> None:
    assert disarm_ours() == (None, False, "nothing of ours armed")
    with patch.object(_rtc_hw, "_run", return_value=_done()):
        arm(EPOCH, "2026-10-06")
    _rtc_hw.WAKEALARM_FILE.write_text(str(EPOCH))
    run = MagicMock(return_value=_done())
    with patch.object(_rtc_hw, "_run", run):
        record, disarmed, detail = disarm_ours()
    assert (record, disarmed, detail) == (
        ArmedRecord(EPOCH, "2026-10-06"),
        True,
        "disarmed",
    )
    assert run.call_args.args[0][-2:] == ["-m", "disable"]
    assert read_record() is None


def test_a_fired_or_replaced_alarm_is_just_forgotten() -> None:
    _rtc_hw.WAKEALARM_FILE.write_text(str(EPOCH))
    arm(EPOCH, "2026-10-06")
    _rtc_hw.WAKEALARM_FILE.write_text("")
    _, disarmed, detail = disarm_ours()
    assert (disarmed, detail) == (False, "no longer pending")
    assert read_record() is None


def test_record_tolerates_garbage() -> None:
    for body in ("{bad", "[1]", '{"epoch": true}', '{"epoch": "5"}'):
        _rtc_hw.RTC_ARMED_FILE.write_text(body)
        assert read_record() is None
    _rtc_hw.RTC_ARMED_FILE.write_text(json.dumps({"epoch": 5, "target_date": None}))
    assert read_record() == ArmedRecord(5, "")


def test_record_write_failure_only_logs() -> None:
    _rtc_hw.WAKEALARM_FILE.write_text(str(EPOCH))
    with patch.object(Path, "write_text", side_effect=OSError("ro")):
        assert arm(EPOCH, "d") == (True, "already set")
    assert read_record() is None


def test_real_seam() -> None:
    with patch.object(subprocess, "run", return_value=_done()) as run:
        REAL_RUN(["true"])
    assert run.call_args.args[0] == ["true"]
