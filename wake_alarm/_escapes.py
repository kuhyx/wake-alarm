"""React to the phone's escape hatch on the PC side.

An honoured escape (``_enforcement_payload.is_honoured``) for morning ``D``:

* is logged once as ``escape_seen`` -- the seen ids live in the event state,
  pruned to the ids the phone still carries, so the set stays bounded;
* cancels a ``workday_penalty.json`` issued on ``D`` (``penalty_cancelled``).
  Checked on every refresh, not only on ``D`` itself: an escape for Thursday
  typed on Thursday evening must still cancel the penalty Friday would read.

The fallback alarm and ``_workday_penalty.maybe_apply`` consult the escape
dates themselves; this module only does the bookkeeping both share.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from wake_alarm._events import emit, last_value, remember
from wake_alarm._workday_penalty import cancel_for_escapes

if TYPE_CHECKING:
    from wake_alarm._enforcement_payload import EnforcementView

_SEEN_SLOT = "escape_seen"


def note_escapes(view: EnforcementView) -> list[str]:
    """Log newly seen escapes and cancel their penalties; returns new ids."""
    seen = set((last_value(_SEEN_SLOT) or "").split(",")) - {""}
    honoured = view.honoured_escapes()
    fresh: list[str] = []
    for escape in honoured:
        if escape.id in seen:
            continue
        emit(
            "escape_seen",
            f"escape for {escape.date}",
            id=escape.id,
            date=escape.date,
            at=escape.at,
            reason=escape.reason,
        )
        fresh.append(escape.id)
    current = {escape.id for escape in honoured}
    remember(_SEEN_SLOT, ",".join(sorted(current)) or None)
    cancel_for_escapes(view.escaped_dates())
    return fresh
