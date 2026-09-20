"""The carrot's rule: ``exempt_until`` per outcome (``_session_policy``)."""

from __future__ import annotations

from datetime import datetime

from wake_alarm._session_payload import SessionRecord
from wake_alarm._session_policy import exempt_until


def _record(
    outcome: str = "completed",
    started: str = "2026-09-19T08:01:00.000",
    finished: str | None = "2026-09-19T08:40:00.000",
    date: str = "2026-09-19",
) -> SessionRecord:
    return SessionRecord(
        date=date,
        outcome=outcome,
        started_at=started,
        finished_at=finished,
        energy=3,
        weight_kg=73.8,
        re_rings=0,
        device_id="p",
        published_at=1.0,
    )


def _local(iso: str) -> datetime:
    return datetime.fromisoformat(iso).astimezone()


class TestExemptUntil:
    """The policy, signed in once so no consumer re-derives it."""

    def test_completed_in_time_earns_eleven(self) -> None:
        assert exempt_until(_record()) == _local("2026-09-19T11:00:00")

    def test_live_is_start_plus_grace_capped(self) -> None:
        assert exempt_until(_record("in_progress", finished=None)) == _local(
            "2026-09-19T09:30:00"
        )
        early = _record("in_progress", started="2026-09-19T06:00:00.000", finished=None)
        assert exempt_until(early) == _local("2026-09-19T07:30:00")

    def test_completed_after_the_cutoff_earns_nothing(self) -> None:
        """A phone switched on at noon completes the legs then; no carrot."""
        assert exempt_until(_record(finished="2026-09-19T12:33:00.000")) is None
        # An aborted 06:00 alarm "completed" at 10:00 locks no later than today.
        late_early = _record(
            started="2026-09-19T06:05:00.000", finished="2026-09-19T10:00:00.000"
        )
        assert exempt_until(late_early) is None

    def test_failed_and_unreadable_instants_earn_nothing(self) -> None:
        assert exempt_until(_record("failed")) is None
        assert exempt_until(_record(started="when?")) is None
        assert exempt_until(_record(finished=None)) is None
        assert exempt_until(_record(finished="later")) is None
