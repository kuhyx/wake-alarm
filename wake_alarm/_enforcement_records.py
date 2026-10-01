"""One phone value in, one typed record out: the v2 fields' shapes.

Pure, like ``_session_payload``. Every builder returns None (or drops the
entry) on anything malformed instead of raising, and never turns a JSON
``null`` into the string ``"None"`` -- the exact bug that hid six people's
replies in signal-bot. Shapes are fixed by ``DOCS-wake-enforcement.md``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass(frozen=True)
class RingStarted:
    """The phone opened its ring screen on ``date`` at ``at``."""

    date: str
    at: str


@dataclass(frozen=True)
class Escape:
    """One use of the "That was a bug" hatch; ``date`` is the excused morning."""

    id: str
    date: str
    at: str
    reason: str


@dataclass(frozen=True)
class StickState:
    """The phone's consecutive-miss streak and its current lockdown."""

    streak: int
    locked_through: str | None
    last_miss: str | None


@dataclass(frozen=True)
class PhoneEvent:
    """One entry of the phone's own event log."""

    at: str
    kind: str
    data: dict[str, object] = field(default_factory=dict)


def text(value: object) -> str:
    """A string field, ``""`` for null or any non-string."""
    return value if isinstance(value, str) else ""


def optional_text(value: object) -> str | None:
    """A non-empty string, else None (null stays null)."""
    return value if isinstance(value, str) and value else None


def is_iso_date(value: str) -> bool:
    """Whether ``value`` is a ``YYYY-MM-DD`` date."""
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return len(value) == len("YYYY-MM-DD")


def parse_instant(value: str) -> datetime | None:
    """An ISO-8601 instant as an aware local datetime; naive means local."""
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed.astimezone()


def ring_started_from(value: object) -> RingStarted | None:
    """``{"date", "at"}`` or None."""
    if not isinstance(value, dict):
        return None
    day, at = text(value.get("date")), text(value.get("at"))
    if not is_iso_date(day):
        return None
    return RingStarted(date=day, at=at)


def escape_from(value: object) -> Escape | None:
    """``{"id", "date", "at", "reason"}`` or None when id/date are unusable."""
    if not isinstance(value, dict):
        return None
    ident, day = text(value.get("id")), text(value.get("date"))
    if not ident or not is_iso_date(day):
        return None
    return Escape(
        id=ident, date=day, at=text(value.get("at")), reason=text(value.get("reason"))
    )


def stick_state_from(value: object) -> StickState | None:
    """``{"streak", "locked_through", "last_miss"}`` or None."""
    if not isinstance(value, dict):
        return None
    streak = value.get("streak")
    if isinstance(streak, bool) or not isinstance(streak, int) or streak < 0:
        return None
    return StickState(
        streak=streak,
        locked_through=optional_text(value.get("locked_through")),
        last_miss=optional_text(value.get("last_miss")),
    )


def phone_event_from(value: object) -> PhoneEvent | None:
    """``{"at", "kind", "data"}`` or None when ``at``/``kind`` are missing."""
    if not isinstance(value, dict):
        return None
    at, kind = text(value.get("at")), text(value.get("kind"))
    if not at or not kind:
        return None
    data = value.get("data")
    return PhoneEvent(
        at=at,
        kind=kind,
        data={str(k): v for k, v in data.items()} if isinstance(data, dict) else {},
    )
