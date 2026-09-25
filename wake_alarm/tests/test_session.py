"""The signed morning-session file the lock consumers read."""

from __future__ import annotations

from datetime import datetime, timedelta
import json
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

from wake_alarm import _session
from wake_alarm._session import (
    describe,
    main,
    read_entry,
    refresh,
    to_entry,
    write_entry,
)
from wake_alarm._session_payload import SessionRecord
from wake_alarm._sync import Alarm

if TYPE_CHECKING:
    from collections.abc import Generator

import pytest

NOW = datetime(2026, 9, 19, 8, 30).astimezone()


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


class TestEntryFile:
    """Writing, signing, reading back."""

    def test_round_trip_is_verified(self) -> None:
        entry = to_entry(_record(), today="2026-09-19", refreshed_at=5.0)
        assert entry["exempt_until"] == _local("2026-09-19T11:00:00").isoformat()
        assert write_entry(entry)
        assert read_entry() == entry
        assert "hmac" in entry

    def test_no_session_yet_is_exempt_until_the_alarm_plus_grace(self) -> None:
        """Being up before the alarm is the goal; the PC stays open until it rang."""
        entry = to_entry(None, today="2026-09-19", refreshed_at=5.0, alarm=(8, 0))
        assert entry["outcome"] == "none"
        assert entry["exempt_until"] == _local("2026-09-19T08:15:00").isoformat()
        early = to_entry(None, today="2026-09-19", refreshed_at=5.0, alarm=(6, 30))
        assert early["exempt_until"] == _local("2026-09-19T06:45:00").isoformat()

    def test_unknown_alarm_and_failed_have_no_exemption(self) -> None:
        entry = to_entry(None, today="2026-09-19", refreshed_at=5.0)
        assert "exempt_until" not in entry
        failed = to_entry(_record("failed"), today="2026-09-19", refreshed_at=5.0)
        assert failed["outcome"] == "failed"
        assert "exempt_until" not in failed

    def test_tampering_is_rejected(self, tmp_path: Path) -> None:
        write_entry(to_entry(_record(), today="2026-09-19", refreshed_at=5.0))
        path = _session.MORNING_SESSION_FILE
        tampered = json.loads(path.read_text())
        tampered["exempt_until"] = _local("2026-09-19T23:00:00").isoformat()
        path.write_text(json.dumps(tampered))
        assert read_entry() is None
        path.write_text("[]")
        assert read_entry() is None
        path.write_text("{")
        assert read_entry() is None
        path.unlink()
        assert read_entry() is None
        assert (tmp_path / "morning_session.json") == path

    def test_unsigned_when_the_key_is_missing(self) -> None:
        with patch("wake_alarm._session.compute_entry_hmac", return_value=None):
            entry = to_entry(None, today="2026-09-19", refreshed_at=5.0)
            assert write_entry(entry)
        assert "hmac" not in entry

    def test_write_failure_is_false(self) -> None:
        with patch.object(Path, "write_text", side_effect=OSError("ro")):
            assert not write_entry(to_entry(None, today="2026-09-19", refreshed_at=5.0))


class TestRefresh:
    """Fetch, select, write."""

    @pytest.fixture(autouse=True)
    def _alarm(self) -> Generator[None]:
        with patch("wake_alarm._session.get_alarm", return_value=Alarm(8, 0, "cache")):
            yield

    def _logs(self, record_json: dict[str, object]) -> list[tuple[str, str]]:
        raw = json.dumps(
            {
                "alarm": {
                    "fields": {
                        "morning_sessions": [
                            [record_json],
                            "2026-09-19T06:20:00.000Z-0000-p",
                        ]
                    }
                }
            }
        )
        return [("p", raw)]

    def test_todays_session_is_written(self) -> None:
        session = {
            "date": "2026-09-19",
            "started_at": "2026-09-19T08:01:00.000",
            "updated_at": "2026-09-19T08:40:00.000",
            "outcome": "completed",
        }
        with patch(
            "wake_alarm._session.fetch_firebase_logs", return_value=self._logs(session)
        ):
            entry = refresh(NOW)
        assert entry is not None
        assert entry["outcome"] == "completed"
        assert read_entry() == entry

    def test_yesterdays_session_becomes_none(self) -> None:
        session = {
            "date": "2026-09-18",
            "started_at": "2026-09-18T08:01:00.000",
            "outcome": "completed",
        }
        with patch(
            "wake_alarm._session.fetch_firebase_logs", return_value=self._logs(session)
        ):
            entry = refresh(NOW)
        assert entry is not None
        assert (entry["date"], entry["outcome"]) == ("2026-09-19", "none")
        assert entry["exempt_until"] == _local("2026-09-19T08:15:00").isoformat()

    def test_a_synced_alarm_later_than_the_baseline_is_clamped(self) -> None:
        with (
            patch("wake_alarm._session.fetch_firebase_logs", return_value=[]),
            patch("wake_alarm._session.get_alarm", return_value=Alarm(13, 0, "cache")),
        ):
            entry = refresh(NOW)
        assert entry is not None
        assert entry["exempt_until"] == _local("2026-09-19T08:15:00").isoformat()

    def test_the_clamp_follows_the_ramp(self) -> None:
        # 2026-10-05 is 07:50 on the ramp, so a synced 08:00 grants 08:05.
        with (
            patch("wake_alarm._session.fetch_firebase_logs", return_value=[]),
            patch("wake_alarm._session.get_alarm", return_value=Alarm(8, 0, "cache")),
        ):
            entry = refresh(datetime(2026, 10, 5, 7, 0).astimezone())
        assert entry is not None
        assert entry["exempt_until"] == _local("2026-10-05T08:05:00").isoformat()

    def test_an_earlier_synced_alarm_shortens_the_grace(self) -> None:
        with (
            patch("wake_alarm._session.fetch_firebase_logs", return_value=[]),
            patch("wake_alarm._session.get_alarm", return_value=Alarm(6, 30, "remote")),
        ):
            entry = refresh(NOW)
        assert entry is not None
        assert entry["exempt_until"] == _local("2026-09-19T06:45:00").isoformat()

    def test_unreadable_backend_leaves_the_file_alone(self) -> None:
        write_entry(to_entry(_record(), today="2026-09-19", refreshed_at=5.0))
        with patch("wake_alarm._session.fetch_firebase_logs", return_value=None):
            assert refresh(NOW) is None
        assert read_entry() is not None

    def test_write_failure_is_none(self) -> None:
        with (
            patch("wake_alarm._session.fetch_firebase_logs", return_value=[]),
            patch("wake_alarm._session.write_entry", return_value=False),
        ):
            assert refresh(NOW) is None


class TestCli:
    """--show and --refresh, and the verdict line."""

    def test_describe_covers_every_verdict(self) -> None:
        entry = to_entry(_record(), today="2026-09-19", refreshed_at=5.0)
        assert "exempt until" in describe(entry, NOW)
        assert "exemption ended" in describe(entry, NOW + timedelta(hours=4))
        assert "no exemption" in describe(
            to_entry(None, today="x", refreshed_at=5.0), NOW
        )

    def test_show_prints_the_verified_entry(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        write_entry(to_entry(_record(), today="2026-09-19", refreshed_at=5.0))
        assert main(["--show"]) == 0
        out = capsys.readouterr().out
        assert '"outcome": "completed"' in out
        assert "2026-09-19 completed" in out

    def test_show_without_a_file_exits_1(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(["--show"]) == 1
        assert "no verified" in capsys.readouterr().out

    def test_refresh_uses_the_backend(self) -> None:
        with (
            patch("wake_alarm._session.fetch_firebase_logs", return_value=[]) as fetch,
            patch("wake_alarm._session.get_alarm", return_value=Alarm(8, 0, "cache")),
        ):
            assert main(["--refresh"]) == 0
        fetch.assert_called_once()
        entry = read_entry()
        assert entry is not None
        assert entry["outcome"] == "none"

    def test_argv_defaults_to_sys_argv(self) -> None:
        with patch("wake_alarm._session.sys.argv", ["prog", "--show"]):
            assert main() == 1
