"""Sick days: the one place wake_alarm asks the shared ``sickdays`` pool.

A sick day (``~/src/utils/sickdays``) is not a free day -- a separate pool,
no cap, no reason -- but on the PC it stands down the same things: no
fallback ring, no RTC self-wake, no workday penalty, no morning routine.

Two rules this module exists to keep in one spot:

* **Fail closed.** ``sickdays.is_sick_day`` never raises and reads a corrupt
  pool as "not sick". The import is guarded as well: these jobs run under
  ``/usr/bin/python``, and a package that failed to install must leave
  enforcement *on* (not sick), never crash the per-minute tick -- a crashed
  tick rings nothing.
* **Sync only where something is about to happen, never in a read-only
  mode.** ``sync_quietly`` rewrites the local pool, so ``--dry-run`` and
  ``--show`` never call it. The sickdays timer alone is not enough: it is a
  monotonic 15-minute timer, which pauses during hibernate and has no
  ``Persistent`` catch-up, so right after the RTC resume the pool can be a
  whole interval stale -- exactly when a day marked sick from bed matters.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

_logger = logging.getLogger(__name__)

try:
    import sickdays

    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False
    _logger.warning("sickdays is not installed; no day counts as sick")

if TYPE_CHECKING:
    from datetime import date


def is_sick(day: date) -> bool:
    """Whether ``day`` is a sick day; local file only, never raises."""
    return _AVAILABLE and sickdays.is_sick_day(day)


def sync() -> bool:
    """Pull the pool from Firebase now; False when it could not (silently)."""
    return _AVAILABLE and sickdays.sync_quietly()


def is_sick_synced(day: date) -> bool:
    """:func:`is_sick` after a fresh :func:`sync` -- for act modes only."""
    sync()
    return is_sick(day)
