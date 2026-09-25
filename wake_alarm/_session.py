"""Distil the phone's morning session into the PC's signed carrot file.

screen-locker and leetcode-guard defer their locks while the morning is
being earned, but neither may talk to Firebase: wake-alarm is the one reader.
``wake-alarm-session.timer`` runs ``--refresh`` every two minutes through the
morning; each run fetches the phone's logs, picks the newest morning
(``_session_payload``) and rewrites ``MORNING_SESSION_FILE`` as an HMAC-signed
entry that always describes **today**:

* today's session, with ``exempt_until`` signed in when it is live
  (``min(started_at + 90 min, 09:30)``) or completed in time (``11:00``);
* a ``none`` entry when the phone has nothing for today, exempt until the
  alarm plus ``SESSION_NONE_GRACE``: waking up early is the goal, so the PC
  stays open until the alarm has rung and been dismissed. The entry is also
  what lets a consumer tell "fresh, no session" from "the refresher has not
  run yet" (a PC booted mid-morning) by the date alone.

Consumers apply one rule -- HMAC ok, date is today, ``now < exempt_until`` --
and never re-derive the cutoffs; those live in ``_session_policy``. Dates are
the phone's local day throughout; ``_state._today_str`` is UTC and must not
be used here.

    python -m wake_alarm._session --refresh   # fetch and rewrite the file
    python -m wake_alarm._session --show      # print the verified entry
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import logging
import sys

from gatelock.log_integrity import compute_entry_hmac, verify_entry_hmac

from wake_alarm._constants import MORNING_SESSION_FILE
from wake_alarm._logging_setup import configure_logging
from wake_alarm._ramp import baseline_time
from wake_alarm._session_payload import newest_session
from wake_alarm._session_policy import to_entry
from wake_alarm._sync import get_alarm
from wake_alarm._sync_transport import fetch_firebase_logs
from wake_alarm._workday_penalty import maybe_apply as _maybe_apply_workday_penalty

_logger = logging.getLogger(__name__)


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
    alarm = get_alarm()
    entry = to_entry(
        record,
        today=today,
        refreshed_at=now.timestamp(),
        # Same clamp as the trigger: the phone may only move the alarm earlier
        # than today's ramp baseline, so a later value never widens the grace.
        alarm=min((alarm.hour, alarm.minute), baseline_time(now.date())),
    )
    if not write_entry(entry):
        return None
    _maybe_apply_workday_penalty(entry, now)
    return entry


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
