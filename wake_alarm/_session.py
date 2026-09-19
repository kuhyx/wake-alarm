"""Distil the phone's morning session into the PC's signed carrot file.

screen-locker and leetcode-guard defer their locks while the morning is
being earned, but neither may talk to Firebase: wake-alarm is the one reader.
``wake-alarm-session.timer`` runs ``--refresh`` every two minutes through the
morning; each run fetches the phone's logs, picks the newest morning
(``_session_payload``) and rewrites ``MORNING_SESSION_FILE`` as an HMAC-signed
entry that always describes **today**:

* today's session, with ``exempt_until`` signed in when it is live
  (``min(started_at + 90 min, 09:30)``) or completed (``11:00``);
* a ``none`` heartbeat when the phone has nothing for today, so a consumer can
  tell "fresh, no session" from "the refresher has not run yet" (a PC booted
  mid-morning) by the date alone.

Consumers apply one rule -- HMAC ok, date is today, ``now < exempt_until`` --
and never re-derive the cutoffs. Dates are the phone's local day throughout;
``_state._today_str`` is UTC and must not be used here.

    python -m wake_alarm._session --refresh   # fetch and rewrite the file
    python -m wake_alarm._session --show      # print the verified entry
"""

from __future__ import annotations

import argparse
from datetime import datetime, time
import json
import logging
import sys

from gatelock.log_integrity import compute_entry_hmac, verify_entry_hmac

from wake_alarm._constants import (
    MORNING_SESSION_FILE,
    SESSION_COMPLETED_UNTIL,
    SESSION_PROVISIONAL_CAP,
    SESSION_PROVISIONAL_GRACE,
)
from wake_alarm._logging_setup import configure_logging
from wake_alarm._session_payload import SessionRecord, newest_session
from wake_alarm._sync_transport import fetch_firebase_logs

_logger = logging.getLogger(__name__)

NONE_OUTCOME = "none"


def _local(iso: str) -> datetime:
    """A phone-stamped naive local ISO instant as an aware local datetime."""
    return datetime.fromisoformat(iso).astimezone()


def _at(date: str, clock: tuple[int, int]) -> datetime:
    """Local wall-clock instant ``clock`` on the phone's session date."""
    return datetime.combine(
        datetime.fromisoformat(date).date(), time(*clock)
    ).astimezone()


def _cutoff(record: SessionRecord) -> datetime | None:
    """The instant a live morning stops being exempt: start + grace, capped."""
    try:
        started = _local(record.started_at)
    except ValueError:
        _logger.info(
            "Session started_at %r unreadable; no exemption", record.started_at
        )
        return None
    return min(
        started + SESSION_PROVISIONAL_GRACE, _at(record.date, SESSION_PROVISIONAL_CAP)
    )


def exempt_until(record: SessionRecord) -> datetime | None:
    """When the carrot this morning earned runs out; None when it earned none.

    Live: the start plus one honest morning, capped -- relative so an early
    alarm cannot bank hours by aborting. Completed: the flat end, but only if
    it finished inside that same cutoff -- a phone switched back on at noon
    completes the legs then, and that must not un-lock anything. Failed: none.
    """
    cutoff = _cutoff(record)
    if cutoff is None or record.outcome == "failed":
        return None
    if record.outcome == "in_progress":
        return cutoff
    try:
        finished = _local(record.finished_at or "")
    except ValueError:
        _logger.info(
            "Session finished_at %r unreadable; no exemption", record.finished_at
        )
        return None
    if finished > cutoff:
        _logger.info(
            "Session finished %s, after the %s cutoff; no exemption", finished, cutoff
        )
        return None
    return _at(record.date, SESSION_COMPLETED_UNTIL)


def to_entry(
    record: SessionRecord | None, *, today: str, refreshed_at: float
) -> dict[str, object]:
    """The unsigned file body for ``record`` (today's) or the ``none`` heartbeat."""
    if record is None:
        return {
            "date": today,
            "outcome": NONE_OUTCOME,
            "started_at": None,
            "finished_at": None,
            "energy": None,
            "weight_kg": None,
            "re_rings": 0,
            "device_id": "",
            "published_at": None,
            "refreshed_at": refreshed_at,
        }
    entry: dict[str, object] = {
        "date": record.date,
        "outcome": record.outcome,
        "started_at": record.started_at,
        "finished_at": record.finished_at,
        "energy": record.energy,
        "weight_kg": record.weight_kg,
        "re_rings": record.re_rings,
        "device_id": record.device_id,
        "published_at": record.published_at,
        "refreshed_at": refreshed_at,
    }
    until = exempt_until(record)
    if until is not None:
        entry["exempt_until"] = until.isoformat()
    return entry


def write_entry(entry: dict[str, object]) -> bool:
    """Sign and write ``entry``; False when the disk refused."""
    signature = compute_entry_hmac(entry)
    if signature is not None:
        entry["hmac"] = signature
    else:
        _logger.warning("HMAC key unavailable — writing unsigned morning session")
    try:
        MORNING_SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        MORNING_SESSION_FILE.write_text(json.dumps(entry, indent=2))
    except OSError as exc:
        _logger.warning("Could not write %s: %s", MORNING_SESSION_FILE, exc)
        return False
    return True


def read_entry() -> dict[str, object] | None:
    """The file's entry if it exists and its signature verifies, else None."""
    try:
        entry = json.loads(MORNING_SESSION_FILE.read_text())
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as exc:
        _logger.warning("Cannot read %s: %s", MORNING_SESSION_FILE, exc)
        return None
    if not isinstance(entry, dict):
        return None
    if not verify_entry_hmac(entry):
        _logger.warning("Morning session HMAC verification failed")
        return None
    return entry


def refresh(now: datetime) -> dict[str, object] | None:
    """Fetch, select, and rewrite the file; None when the backend was unreadable.

    An unreadable backend leaves the file alone: whatever it says is still
    the newest thing known, and a consumer judges freshness by its date.
    """
    published = fetch_firebase_logs()
    if published is None:
        _logger.info("Morning session not refreshed: backend unreadable")
        return None
    today = now.date().isoformat()
    record = newest_session(published)
    if record is not None and record.date != today:
        _logger.info("Newest morning is %s, not today; writing none", record.date)
        record = None
    entry = to_entry(record, today=today, refreshed_at=now.timestamp())
    return entry if write_entry(entry) else None


def describe(entry: dict[str, object], now: datetime) -> str:
    """One line a human can read off ``--show``."""
    until = entry.get("exempt_until")
    if not isinstance(until, str):
        verdict = "no exemption"
    elif now < datetime.fromisoformat(until):
        verdict = f"exempt until {until}"
    else:
        verdict = f"exemption ended {until}"
    return f"{entry.get('date')} {entry.get('outcome')} — {verdict}"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="PC copy of the phone's morning session"
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--refresh", action="store_true", help="fetch and rewrite the file"
    )
    mode.add_argument("--show", action="store_true", help="print the verified file")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point; exit 1 when there is nothing verifiable to report."""
    configure_logging(component="session")
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    now = datetime.now().astimezone()
    entry = refresh(now) if args.refresh else read_entry()
    if entry is None:
        sys.stdout.write("no verified morning session\n")
        return 1
    sys.stdout.write(json.dumps(entry, indent=2) + "\n" + describe(entry, now) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
