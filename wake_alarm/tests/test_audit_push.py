"""The audit's "has the phone pushed to Firebase lately" check."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
import json
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from wake_alarm import _audit
from wake_alarm._audit import gather
from wake_alarm._audit_checks import check_phone_push, run_checks
from wake_alarm._audit_evidence import Evidence, PhoneSide
from wake_alarm._constants import PHONE_PUSH_STALE_SECONDS
from wake_alarm._sync import Alarm

if TYPE_CHECKING:
    from collections.abc import Generator

NOW = datetime(2026, 11, 15, 20, 0, tzinfo=UTC)
LAST_PUSH = datetime(2026, 11, 13, 17, 38, tzinfo=UTC)


def _ev(last_push: datetime | None) -> Evidence:
    return Evidence(
        day=date(2026, 11, 16),
        stick_day=True,
        free_day=False,
        alarm_at=None,
        alarm_source="t",
        phone_side=PhoneSide(last_push=last_push),
        now=NOW,
    )


def test_threshold_is_a_day() -> None:
    assert PHONE_PUSH_STALE_SECONDS == 24 * 60 * 60


def test_a_stale_phone_is_a_mismatch() -> None:
    check = check_phone_push(_ev(LAST_PUSH))
    assert check.ok is False
    assert "2026-11-13 17:38" in check.detail
    assert "50 h" in check.detail


def test_a_fresh_phone_is_ok() -> None:
    check = check_phone_push(_ev(NOW - timedelta(hours=3)))
    assert check.ok is True
    assert "3 h" in check.detail


def test_exactly_a_day_old_is_still_ok() -> None:
    assert check_phone_push(_ev(NOW - timedelta(hours=24))).ok is True


def test_a_push_stamped_in_the_future_is_ok() -> None:
    assert check_phone_push(_ev(NOW + timedelta(minutes=5))).ok is True


def test_no_dated_record_is_unknown_not_ok_not_bad() -> None:
    check = check_phone_push(_ev(None))
    assert check.ok is None
    assert "could not check" in check.detail


@pytest.fixture(autouse=True)
def _sources() -> Generator[None]:
    with (
        patch.object(_audit, "get_alarm", return_value=Alarm(7, 0, "cache")),
        patch.object(_audit, "boots", return_value=[]),
        patch.object(_audit, "resumes", return_value=[]),
    ):
        yield


def _published(hlc: str) -> list[tuple[str, str]]:
    fields = {"alarm_hour": [7, hlc]}
    return [("p", json.dumps({"alarm": {"fields": fields}}))]


def test_gather_feeds_the_check_and_it_runs_with_the_rest() -> None:
    published = _published("2026-11-13T17:38:00.000Z-0001-p")
    with patch.object(_audit, "fetch_firebase_logs", return_value=published):
        evidence, _ = gather(date(2026, 11, 16))
    assert evidence.phone_side.last_push == LAST_PUSH
    assert "phone pushed to Firebase" in [c.name for c in run_checks(evidence)]


def test_gather_unreachable_firebase_is_unknown() -> None:
    with patch.object(_audit, "fetch_firebase_logs", return_value=None):
        evidence, reachable = gather(date(2026, 11, 16))
    assert not reachable
    assert check_phone_push(evidence).ok is None
