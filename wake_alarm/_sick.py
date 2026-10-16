"""Sick days: the one place wake_alarm asks the shared ``sickdays`` pool.

A sick day (``~/src/utils/sickdays``) is not a free day -- a separate pool,
no cap, no reason -- but on the PC it stands down the same things: no
fallback ring, no RTC self-wake, no workday penalty, no morning routine.

All of that is **one switch**: the ``alarm`` locker. A sick day may *keep*
the alarm (``sickdays`` 0.2.0), and then every piece above behaves exactly as
on a normal day, so the question this module answers is
``stands_down(LOCKER_ALARM, day)``, never plain ``is_sick_day``.

Two rules this module exists to keep in one spot:

* **Fail closed.** ``sickdays.stands_down`` never raises and reads a corrupt
  pool as "not sick". The import is guarded as well: these jobs run under
  ``/usr/bin/python``, and a package that failed to install must leave
  enforcement *on* (not standing down), never crash the per-minute tick -- a crashed
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


def alarm_stands_down(day: date) -> bool:
    """Whether the alarm is switched off on ``day``; local file, never raises.

    True iff ``day`` is sick and its keep set does not hold the alarm.
    """
    return _AVAILABLE and sickdays.stands_down(sickdays.LOCKER_ALARM, day)


def sync() -> bool:
    """Pull the pool from Firebase now; False when it could not (silently)."""
    return _AVAILABLE and sickdays.sync_quietly()


def alarm_stands_down_synced(day: date) -> bool:
    """:func:`alarm_stands_down` after a fresh :func:`sync` -- act modes only."""
    sync()
    return alarm_stands_down(day)
