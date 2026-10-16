"""Sick days and the workday penalty, the session refresh and the audit."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
import json
import logging
from pathlib import Path
from unittest.mock import patch

import pytest
import sickdays

from wake_alarm import _audit, _session, _workday_penalty
from wake_alarm._audit_checks import (
    check_lockdown,
    check_penalty,
    check_ring,
    check_rtc,
    check_up_by_alarm,
)
from wake_alarm._audit_evidence import Evidence, PcSide, PhoneSide
from wake_alarm._enforcement_records import PhoneEvent
from wake_alarm._sync import Alarm
from wake_alarm._workday_penalty import (
    cancel_for_sick_day,
    issued_date,
    maybe_apply,
    penalty_entry,
    skip_reason,
    write_penalty,
)

TUESDAY = date(2026, 9, 22)
AFTER_GRACE = datetime(2026, 9, 22, 9, 0).astimezone()
MISS: dict[str, object] = {
    "outcome": "none",
    "exempt_until": datetime(2026, 9, 22, 8, 15).astimezone().isoformat(),
}


def mark_sick(day: date) -> None:
    """Put ``day`` in the (redirected) pool; may be in the past."""
    sickdays.import_legacy([day])


def pull_marks_tuesday() -> bool:
    """A sync that brings TUESDAY in from another device."""
    mark_sick(TUESDAY)
    return True


@pytest.fixture
def issued() -> None:
    """A penalty issued on TUESDAY, on disk."""
    assert write_penalty(penalty_entry(today=TUESDAY))


class TestWriting:
    def test_a_sick_day_is_never_penalised(self) -> None:
        assert skip_reason(MISS, AFTER_GRACE) is None
        mark_sick(TUESDAY)
        assert skip_reason(MISS, AFTER_GRACE) == "sick day"
        assert not maybe_apply(MISS, AFTER_GRACE)
        assert issued_date() is None

    def test_the_first_write_pulls_the_pool(self) -> None:
        with patch("sickdays.sync_quietly", side_effect=pull_marks_tuesday) as pulled:
            assert not maybe_apply(MISS, AFTER_GRACE)
        pulled.assert_called_once_with()
        assert issued_date() is None

    def test_a_rewrite_does_not_pull_again(self) -> None:
        assert maybe_apply(MISS, AFTER_GRACE)
        with patch("sickdays.sync_quietly") as pulled:
            assert maybe_apply(MISS, AFTER_GRACE)
        pulled.assert_not_called()

    def test_other_skip_reasons(self) -> None:
        assert skip_reason(MISS, AFTER_GRACE, escaped_dates=frozenset({"2026-09-22"}))
        monday = datetime(2026, 9, 21, 9, 0).astimezone()
        assert skip_reason(MISS, monday) == "not a stick day"
        assert skip_reason({"outcome": "completed"}, AFTER_GRACE) == "no miss"
        with patch.object(_workday_penalty.freedays, "is_free_day", return_value=True):
            assert skip_reason(MISS, AFTER_GRACE) == "free day"


@pytest.mark.usefixtures("issued")
class TestRetraction:
    def test_kept_while_not_sick(self) -> None:
        assert not cancel_for_sick_day()
        assert issued_date() == TUESDAY.isoformat()

    def test_retracted_once_the_issuing_day_is_sick(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        mark_sick(TUESDAY)
        with caplog.at_level(logging.INFO):
            assert cancel_for_sick_day()
        assert issued_date() is None
        assert "penalty_cancelled: sick day for 2026-09-22" in caplog.text

    def test_a_sick_penalty_date_alone_does_not_retract(self) -> None:
        mark_sick(date(2026, 9, 23))
        assert not cancel_for_sick_day()

    def test_unlink_failure_keeps_it(self) -> None:
        mark_sick(TUESDAY)
        with patch.object(Path, "unlink", side_effect=OSError("ro")):
            assert not cancel_for_sick_day()

    def test_garbage_issued_date_is_kept(self) -> None:
        _workday_penalty.WORKDAY_PENALTY_FILE.write_text(
            json.dumps({"issued_date": "soon"})
        )
        assert not cancel_for_sick_day()

    def test_refresh_retracts_even_offline(self) -> None:
        mark_sick(TUESDAY)
        with patch.object(_session, "fetch_firebase_logs", return_value=None):
            assert _session.refresh(AFTER_GRACE) is None
        assert issued_date() is None


def test_no_penalty_file_nothing_to_retract() -> None:
    assert not cancel_for_sick_day()


def _ev(**overrides: object) -> Evidence:
    pc = PcSide(penalty_issued=overrides.pop("penalty_issued", None))
    phone = PhoneSide(events=overrides.pop("phone", []))
    base = Evidence(
        day=TUESDAY,
        stick_day=True,
        free_day=False,
        alarm_at=AFTER_GRACE,
        alarm_source="t",
        pc_side=pc,
        phone_side=phone,
        sick_day=True,
    )
    return replace(base, **overrides)


class TestAudit:
    def test_nothing_is_expected(self) -> None:
        for check in (check_rtc, check_up_by_alarm, check_ring, check_lockdown):
            result = check(_ev())
            assert (result.ok, result.detail) == (None, "sick day")

    def test_penalty(self) -> None:
        assert check_penalty(_ev()).ok is True
        assert check_penalty(_ev(penalty_issued="2026-09-22")).ok is False

    def test_a_lockdown_for_a_sick_miss_is_flagged(self) -> None:
        at = AFTER_GRACE.isoformat()
        phone = [
            PhoneEvent(at, "stick_check", {"date": "2026-09-22", "verdict": "miss"}),
            PhoneEvent(at, "lockdown_sent", {"until": "2026-09-23"}),
        ]
        assert check_lockdown(_ev(phone=phone)).ok is False
        assert check_lockdown(_ev(phone=phone[:1])).ok is None

    def test_the_report_names_the_day(self) -> None:
        mark_sick(TUESDAY)
        with (
            patch.object(_audit, "fetch_firebase_logs", return_value=[]),
            patch.object(_audit, "get_alarm", return_value=Alarm(7, 0, "cache")),
            patch.object(_audit, "boots", return_value=[]),
            patch.object(_audit, "resumes", return_value=[]),
        ):
            evidence, _ = _audit.gather(TUESDAY)
        assert evidence.sick_day
        assert "(Tue, sick day)" in _audit.render(evidence, [], reachable=True)
