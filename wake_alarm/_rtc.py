"""Arm the RTC so the PC is up before a stick-day alarm.

``wake-alarm-rtc.timer`` runs ``--arm`` every 15 min, all day, and once
after boot; a calendar timer that elapsed while the PC slept catches up on
resume, so a PC hibernated at 16:00 on Monday is armed for Tuesday the
moment it next runs at all. The target is the first morning whose wake instant
(``A - RTC_WAKE_LEAD``, ``A`` clamped to 08:00) is still ahead -- so a
02:00 tick on a Tuesday targets Tuesday, not Wednesday. Only a stick day
(``freedays.is_workday``: Tue/Wed/Thu) that is neither a free day nor a sick
day (``_sick``) is armed, via
``sudo -n /usr/sbin/rtcwake -m no -t <epoch>``. The alarm lives in CMOS, so
it survives however the PC goes down.

When the next morning is not one to wake for (a carrot day, or a stick day
that became free or sick), an alarm *we* armed is cleared (``rtc_disarmed``); one
someone else set is left alone (``_rtc_hw``). A changed alarm time needs no
disarm: arming overwrites the single RTC alarm.

``rtc_armed`` / ``rtc_skip`` are logged only when they change; the audit
matches ``rtc_armed`` on its ``target_date``.

``--arm`` pulls the sick-day pool before judging a stick-day target (a day
marked sick on the phone at 23:00 must disarm before the PC goes down);
``--dry-run`` / ``--show`` read the local pool and write nothing. ``--arm``
also retracts a workday penalty issued on a day since marked sick
(``_workday_penalty.cancel_for_sick_day``): this is the one wake_alarm job
that runs all day, and a day can be marked sick until midnight.

    python -m wake_alarm._rtc --arm       # what the timer runs
    python -m wake_alarm._rtc --dry-run   # the plan, nothing armed
    python -m wake_alarm._rtc --show      # the plan + the RTC's current alarm
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
import sys
from typing import TYPE_CHECKING

import freedays

from wake_alarm._cli_modes import mode_parser, parse_with_now
from wake_alarm._constants import RTC_WAKE_LEAD
from wake_alarm._events import emit, emit_on_change
from wake_alarm._fallback_policy import alarm_instant
from wake_alarm._logging_setup import configure_logging
from wake_alarm._pc_wake_mode import read_mode
from wake_alarm._rtc_hw import arm, current_alarm, disarm_ours, read_record
from wake_alarm._sick import is_sick, is_sick_synced
from wake_alarm._sync import Alarm, get_alarm
from wake_alarm._workday_penalty import cancel_for_sick_day

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass(frozen=True)
class Plan:
    """Arm for ``target`` at ``wake_at``, or skip it with a reason."""

    target: date
    wake_at: datetime
    arm: bool
    reason: str

    @property
    def epoch(self) -> int:
        """``wake_at`` as whole epoch seconds."""
        return int(self.wake_at.timestamp())


def _now() -> datetime:
    """Aware local now; the seam tests patch."""
    return datetime.now(tz=UTC).astimezone()


def plan(
    now: datetime, alarm: Alarm, *, sick: Callable[[date], bool] = is_sick
) -> Plan:
    """Which morning is next, and whether it is one to wake the PC for.

    ``sick`` is asked last, so only a stick-day target that is not free ever
    pays for the synced variant ``--arm`` passes.
    """
    target = now.date()
    wake_at = alarm_instant(alarm, target) - RTC_WAKE_LEAD
    if wake_at <= now:
        target += timedelta(days=1)
        wake_at = alarm_instant(alarm, target) - RTC_WAKE_LEAD
    if not freedays.is_workday(target):
        return Plan(
            target, wake_at, arm=False, reason=f"{target:%a} is not a stick day"
        )
    if freedays.is_free_day(target):
        return Plan(target, wake_at, arm=False, reason="free day")
    if sick(target):
        return Plan(target, wake_at, arm=False, reason="sick day")
    return Plan(target, wake_at, arm=True, reason="stick day")


def release(chosen: Plan) -> None:
    """No morning to wake for: clear the alarm we armed, if still pending."""
    record, disarmed, detail = disarm_ours()
    if record is None or detail == "no longer pending":
        return
    if disarmed:
        emit(
            "rtc_disarmed",
            f"cleared {record.target_date} ({chosen.reason})",
            epoch=record.epoch,
            target_date=record.target_date,
            reason=chosen.reason,
        )
        return
    emit_on_change(
        "rtc_skip",
        f"{chosen.target}|disarm_failed",
        f"rtcwake -m disable failed: {detail}",
        epoch=record.epoch,
        target_date=record.target_date,
    )


def apply(chosen: Plan) -> bool:
    """Arm or skip, logging ``rtc_armed`` / ``rtc_skip`` on change."""
    fields = {
        "target_date": chosen.target.isoformat(),
        "wake_at": chosen.wake_at.isoformat(),
        "epoch": chosen.epoch,
        "mode": read_mode(),
    }
    if not chosen.arm:
        emit_on_change(
            "rtc_skip", f"{chosen.target}|{chosen.reason}", chosen.reason, **fields
        )
        release(chosen)
        return False
    ok, detail = arm(chosen.epoch, chosen.target.isoformat())
    if not ok:
        emit_on_change(
            "rtc_skip", f"{chosen.target}|failed", f"rtcwake failed: {detail}", **fields
        )
        return False
    emit_on_change(
        "rtc_armed", str(chosen.epoch), f"wake at {chosen.wake_at:%a %H:%M}", **fields
    )
    return True


def describe(chosen: Plan) -> str:
    """One human line for ``--dry-run`` / ``--show``."""
    verdict = "ARM" if chosen.arm else "skip"
    return (
        f"{verdict} {chosen.target} ({chosen.reason}): wake at "
        f"{chosen.wake_at:%Y-%m-%d %H:%M %Z} epoch {chosen.epoch}\n"
    )


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    parser = mode_parser("Arm the RTC for a stick day", "arm", "arm (the timer)")
    args, now = parse_with_now(parser, argv, _now)
    if args.arm:
        configure_logging(component="rtc")
        cancel_for_sick_day()
        chosen = plan(now, get_alarm(), sick=is_sick_synced)
        return 0 if apply(chosen) or not chosen.arm else 1
    chosen = plan(now, get_alarm())
    sys.stdout.write(describe(chosen))
    record = read_record()
    if not chosen.arm and record is not None and current_alarm() == record.epoch:
        sys.stdout.write(
            f"would disarm ours: {record.epoch} for {record.target_date}\n"
        )
    if args.show:
        pending = current_alarm()
        when = (
            datetime.fromtimestamp(pending, tz=UTC).astimezone().isoformat()
            if pending
            else "none"
        )
        ours = "none" if record is None else f"{record.epoch} for {record.target_date}"
        sys.stdout.write(
            f"rtc wakealarm: {when}\narmed by us: {ours}\nmode: {read_mode()}\n"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
