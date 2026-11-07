"""A corner strip while the morning session is started but not finished.

wake-alarm's signed ``morning_session.json`` makes the lockers stand down
while the morning is live. The screen simply clears, though, and kuhy still
owes the rest of the routine: the locks return at ``exempt_until`` out of
nowhere. This strip is the reminder: a small always-on-top box in the
top-right corner of the primary output (``gatelock.corner_strip``), saying the
session is not finished, what the phone's next step is, and when locks return.

    python -m wake_alarm._session_strip

``wake-alarm-strip.path`` starts it whenever the file is rewritten (every two
minutes through the morning); starting a running service is a no-op. It shows
only while the entry is *signed, dated today, in_progress, and now <
exempt_until*, re-reading the file every second, and exits 0 the moment that
stops being true. While visible it also asks systemd every 30 s to run
``wake-alarm-session.service`` so ``next_step`` follows the phone instead of
the two-minute timer.

Fail modes, out loud: nothing to show is exit 0 (normal, logged at info); no
display or no live output is a warning and exit 1, so the unit shows failed;
a missing, unreadable or tampered file shows nothing (the lockers do not
honour it either) and warns once per distinct problem, not once a second.
"""

from __future__ import annotations

from datetime import datetime
import json
import logging
import subprocess
import sys
import time
import tkinter as tk
from typing import TYPE_CHECKING

from gatelock import LockConfig, enumerate_outputs
from gatelock.corner_strip import StripContent, build_corner_strip, corner_rect
from gatelock.log_integrity import verify_entry_hmac

from wake_alarm._constants import MORNING_SESSION_FILE
from wake_alarm._logging_setup import configure_logging

if TYPE_CHECKING:
    from subprocess import Popen

_logger = logging.getLogger(__name__)

TITLE = "Morning session not finished"
REFRESH_EVERY_SECONDS = 30.0
REFRESH_COMMAND = [
    "systemctl",
    "--user",
    "start",
    "--no-block",
    "wake-alarm-session.service",
]


class _Once:
    """Warns about a problem once, until a clean read clears it.

    The strip reads the file every second; a file that stays broken for an
    hour must be one journal line, not 3600.
    """

    def __init__(self) -> None:
        self.last: str | None = None

    def warn(self, message: str) -> None:
        """Log ``message`` at warning level unless it was just logged."""
        if message != self.last:
            _logger.warning(message)
            self.last = message

    def clear(self) -> None:
        """A clean read happened: the next problem is news again."""
        self.last = None


_once = _Once()


def _local_now() -> datetime:
    """The current time as an aware local datetime (a test seam)."""
    return datetime.now().astimezone()


def _monotonic() -> float:
    """Seconds on the monotonic clock (a test seam)."""
    return time.monotonic()


def _popen(cmd: list[str]) -> Popen[bytes]:
    """Start ``cmd`` without waiting for it (a test seam)."""
    return subprocess.Popen(cmd)


def _make_root() -> tk.Tk:
    """A withdrawn Tk root; only the strip's Toplevel is ever visible."""
    root = tk.Tk()
    root.withdraw()
    return root


def read_entry() -> dict[str, object] | None:
    """The file's parsed JSON object, or None. Verification is the caller's."""
    try:
        text = MORNING_SESSION_FILE.read_text()
    except FileNotFoundError:
        return None
    except OSError as exc:
        _once.warn(f"Cannot read {MORNING_SESSION_FILE}: {exc}")
        return None
    try:
        entry = json.loads(text)
    except json.JSONDecodeError as exc:
        _once.warn(f"Cannot parse {MORNING_SESSION_FILE}: {exc}")
        return None
    if not isinstance(entry, dict):
        _once.warn(f"{MORNING_SESSION_FILE} is not a JSON object")
        return None
    _once.clear()
    return entry


def _why_not_today(entry: dict[str, object], now: datetime) -> str | None:
    """Why ``entry`` is not a verified, live, in-progress morning; None if it is."""
    if not verify_entry_hmac(entry):
        return "morning session entry is unsigned or tampered"
    if entry.get("date") != now.date().isoformat():
        return f"morning session is dated {entry.get('date')}, not today"
    if entry.get("outcome") != "in_progress":
        return f"morning session outcome is {entry.get('outcome')}"
    return None


def _exempt_until(entry: dict[str, object]) -> datetime | str:
    """The entry's aware ``exempt_until``, or the sentence saying why not."""
    until = entry.get("exempt_until")
    if not isinstance(until, str):
        return "morning session has no exempt_until"
    try:
        parsed = datetime.fromisoformat(until)
    except ValueError:
        return f"morning session exempt_until is unreadable: {until!r}"
    if parsed.tzinfo is None:
        # Guessing its zone would be inventing a carrot the signer never gave.
        return "morning session exempt_until has no timezone"
    return parsed


def _verdict(entry: dict[str, object] | None, now: datetime) -> StripContent | str:
    """The strip's content, or the sentence saying why there is none."""
    if entry is None:
        return "no morning session file"
    reason = _why_not_today(entry, now)
    if reason is not None:
        return reason
    exempt_until = _exempt_until(entry)
    if isinstance(exempt_until, str):
        return exempt_until
    if now >= exempt_until:
        return f"the exemption ended at {exempt_until.isoformat()}"
    lines: list[str] = []
    step = entry.get("next_step")
    if isinstance(step, str) and step:
        lines.append(f"Next: {step}")
    lines.append(f"Locks return at {exempt_until.astimezone(now.tzinfo):%H:%M}")
    return StripContent(TITLE, tuple(lines))


def strip_content(
    entry: dict[str, object] | None, now: datetime
) -> StripContent | None:
    """What the strip says for ``entry`` at local ``now``; None shows nothing.

    Something is shown only for a verified entry dated today, still
    ``in_progress``, whose ``exempt_until`` has not passed.
    """
    verdict = _verdict(entry, now)
    return verdict if isinstance(verdict, StripContent) else None


class Refresher:
    """Starts wake-alarm-session.service every 30 s, never two at once."""

    def __init__(self, *, start: float) -> None:
        self._due = start + REFRESH_EVERY_SECONDS
        self._proc: Popen[bytes] | None = None

    def tick(self, now: float) -> None:
        """Reap a finished refresh, and start the next one when it is due."""
        if self._proc is not None:
            code = self._proc.poll()
            if code is None:
                return
            if code != 0:
                _logger.warning("the session refresh start exited %d", code)
            self._proc = None
        if now < self._due:
            return
        self._due = now + REFRESH_EVERY_SECONDS
        try:
            self._proc = _popen(REFRESH_COMMAND)
        except OSError as exc:
            _logger.warning("could not start the session refresh: %s", exc)


def main() -> int:
    """Show the strip while the morning is in progress; 0 when it is over."""
    configure_logging(component="session-strip")
    verdict = _verdict(read_entry(), _local_now())
    if not isinstance(verdict, StripContent):
        _logger.info("Nothing to show: %s", verdict)
        return 0
    try:
        root = _make_root()
    except tk.TclError as exc:
        _logger.warning("Cannot open the display for the strip: %s", exc)
        return 1
    rect = corner_rect(enumerate_outputs(root))
    if rect is None:
        _logger.warning("Cannot place the strip: no live output on this display")
        root.destroy()
        return 1
    strip = build_corner_strip(root, LockConfig(), verdict, rect=rect)
    refresher = Refresher(start=_monotonic())
    ending: list[str] = []

    def supply() -> StripContent | None:
        current = _verdict(read_entry(), _local_now())
        if not isinstance(current, StripContent):
            ending.append(current)
            return None
        refresher.tick(_monotonic())
        return current

    strip.schedule(supply, on_close=root.quit)
    root.mainloop()
    root.destroy()
    _logger.info("Strip closed: %s", ending[0] if ending else "window gone")
    return 0


if __name__ == "__main__":
    sys.exit(main())
