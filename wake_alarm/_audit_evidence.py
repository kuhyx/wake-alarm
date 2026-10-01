"""What the daily audit knows about one morning, as plain data.

Split from ``_audit_checks`` (the rules) so the evidence shape can be read on
its own: the PC's side (named events, when anything was logged, boots and
resumes, the penalty file) and the phone's side (its event log, escapes, the
ring screen and the stick streak), plus the day and its alarm.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from wake_alarm._enforcement_records import parse_instant

if TYPE_CHECKING:
    from datetime import date, datetime

    from wake_alarm._audit_sources import PcEvent, Up
    from wake_alarm._enforcement_records import Escape, PhoneEvent, StickState


@dataclass(frozen=True)
class PcSide:
    """The PC's own record of the morning."""

    events: list[PcEvent] = field(default_factory=list)
    seen: list[datetime] = field(default_factory=list)
    ups: list[Up] = field(default_factory=list)
    penalty_issued: str | None = None


@dataclass(frozen=True)
class PhoneSide:
    """What the phone published about the morning."""

    events: list[PhoneEvent] = field(default_factory=list)
    escapes: list[Escape] = field(default_factory=list)
    ring_started: bool = False
    stick_state: StickState | None = None


@dataclass(frozen=True)
class Evidence:
    """Everything the audit gathered about ``day``."""

    day: date
    stick_day: bool
    free_day: bool
    alarm_at: datetime | None
    alarm_source: str
    pc_side: PcSide = field(default_factory=PcSide)
    phone_side: PhoneSide = field(default_factory=PhoneSide)

    @property
    def pc(self) -> list[PcEvent]:
        """Named PC events."""
        return self.pc_side.events

    @property
    def pc_seen(self) -> list[datetime]:
        """When the PC logged anything at all."""
        return self.pc_side.seen

    @property
    def ups(self) -> list[Up]:
        """Boots and resumes."""
        return self.pc_side.ups

    @property
    def penalty_issued(self) -> str | None:
        """``issued_date`` of the penalty file, if one is on disk."""
        return self.pc_side.penalty_issued

    @property
    def phone(self) -> list[PhoneEvent]:
        """The phone's own events."""
        return self.phone_side.events

    @property
    def escapes(self) -> list[Escape]:
        """Escapes excusing this day (honoured or not)."""
        return self.phone_side.escapes

    @property
    def ring_started(self) -> bool:
        """Whether the phone's ring screen opened this day."""
        return self.phone_side.ring_started

    @property
    def stick_state(self) -> StickState | None:
        """The phone's streak, as published now."""
        return self.phone_side.stick_state


@dataclass(frozen=True)
class Check:
    """One expectation and what was observed."""

    name: str
    ok: bool | None
    detail: str


def ok(name: str, detail: str) -> Check:
    """An expectation that held."""
    return Check(name, ok=True, detail=detail)


def bad(name: str, detail: str) -> Check:
    """A mismatch: lands under ``## Flags``."""
    return Check(name, ok=False, detail=detail)


def na(name: str, detail: str) -> Check:
    """Not applicable to this morning."""
    return Check(name, ok=None, detail=detail)


def pc_on_day(ev: Evidence, name: str) -> list[PcEvent]:
    """PC events called ``name`` on the audited day itself."""
    return [e for e in ev.pc if e.event == name and e.at.date() == ev.day]


def phone_on_day(ev: Evidence) -> list[PhoneEvent]:
    """Phone events stamped on the audited day itself."""
    on_day: list[PhoneEvent] = []
    for event in ev.phone:
        at = parse_instant(event.at)
        if at is not None and at.date() == ev.day:
            on_day.append(event)
    return on_day


def phone_kinds(ev: Evidence) -> set[str]:
    """Phone event kinds recorded on the audited day."""
    return {event.kind for event in phone_on_day(ev)}
