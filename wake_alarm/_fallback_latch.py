"""Today's fallback-ring latch: ``fallback_ring.json``.

``{"date", "started_at", "stopped_at", "reason", "stop_reason"}`` -- the
contract's shape. It is what makes the 30-minute cap survive the ringing
process dying (a hibernate, a reboot): the cap is measured from the
wall-clock ``started_at``, never a monotonic clock, which does not advance
through S4. An unreadable latch is no latch -- fail toward ringing.

``file`` (default ``FALLBACK_RING_FILE``, resolved per call so the test
redirect holds) lets the 21:00 notifications ring keep its own latch.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import json
import logging
from typing import TYPE_CHECKING

from wake_alarm._constants import FALLBACK_RING_FILE
from wake_alarm._enforcement_records import optional_text, parse_instant

if TYPE_CHECKING:
    from datetime import datetime
    from pathlib import Path

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Latch:
    """One day's fallback ring, as far as it got."""

    date: str
    started_at: str | None = None
    stopped_at: str | None = None
    reason: str | None = None
    stop_reason: str | None = None

    def started(self) -> datetime | None:
        """``started_at`` as an aware datetime, or None."""
        return parse_instant(self.started_at) if self.started_at else None


def read_latch(day: str, file: Path | None = None) -> Latch | None:
    """The latch for ``day``; None when absent, unreadable or another day's."""
    path = file or FALLBACK_RING_FILE
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        _logger.info("Ignoring unreadable %s: %s", path, exc)
        return None
    if not isinstance(raw, dict) or raw.get("date") != day:
        return None
    return Latch(
        date=day,
        started_at=optional_text(raw.get("started_at")),
        stopped_at=optional_text(raw.get("stopped_at")),
        reason=optional_text(raw.get("reason")),
        stop_reason=optional_text(raw.get("stop_reason")),
    )


def write_latch(latch: Latch, file: Path | None = None) -> bool:
    """Persist ``latch``; False when the disk refused."""
    path = file or FALLBACK_RING_FILE
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(latch), indent=2))
    except OSError as exc:
        _logger.warning("Could not write %s: %s", path, exc)
        return False
    return True


def mark_started(
    previous: Latch | None,
    *,
    day: str,
    now: datetime,
    reason: str,
    file: Path | None = None,
) -> Latch:
    """Record a ring (re)starting; a resumed ring keeps its first start."""
    if previous is not None and previous.started_at:
        latch = replace(previous, stopped_at=None, stop_reason=None)
    else:
        latch = Latch(date=day, started_at=now.isoformat(), reason=reason)
    write_latch(latch, file)
    return latch


def mark_stopped(
    latch: Latch, *, now: datetime, stop_reason: str, file: Path | None = None
) -> Latch:
    """Record why and when the ring stopped."""
    stopped = replace(latch, stopped_at=now.isoformat(), stop_reason=stop_reason)
    write_latch(stopped, file)
    return stopped
