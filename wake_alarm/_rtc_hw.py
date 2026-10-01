"""The RTC wake alarm itself, and our record of the one we set.

Split from ``_rtc`` (which morning, and whether): this is the hardware side.
The pending alarm is read without root from ``/sys/class/rtc/rtc0/wakealarm``;
setting and clearing go through the NOPASSWD ``sudo -n /usr/sbin/rtcwake``.

``RTC_ARMED_FILE`` (``{"epoch", "target_date"}``) remembers the alarm *we*
armed, so :func:`disarm_ours` only ever clears that one: an alarm someone
else set (a manual ``rtcwake``) is not ours to remove. The comparison is on
the sysfs value, which is epoch seconds when the RTC keeps UTC (this host:
no ``/etc/adjtime``). An RTC on local time would never match, which fails
safe -- the alarm is left in place, never cleared by mistake.

Every process goes through ``_run``, the seam the suite replaces.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from pathlib import Path
import subprocess

from wake_alarm._constants import RTC_ARMED_FILE

_logger = logging.getLogger(__name__)

RTCWAKE = "/usr/sbin/rtcwake"
WAKEALARM_FILE = Path("/sys/class/rtc/rtc0/wakealarm")


@dataclass(frozen=True)
class ArmedRecord:
    """The alarm this package last armed."""

    epoch: int
    target_date: str


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    """Run ``cmd``; the seam tests replace so nothing ever arms this host."""
    return subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=15)


def _rtcwake(*args: str) -> tuple[bool, str]:
    """``sudo -n rtcwake <args>``; ``(succeeded, detail)``."""
    try:
        result = _run(["sudo", "-n", RTCWAKE, *args])
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)
    detail = (result.stderr or result.stdout or "").strip()
    return result.returncode == 0, detail


def current_alarm() -> int | None:
    """The RTC's pending wake alarm (epoch), or None when none is pending."""
    try:
        text = WAKEALARM_FILE.read_text(encoding="ascii").strip()
    except OSError:
        return None
    return int(text) if text.isdigit() else None


def read_record() -> ArmedRecord | None:
    """What we last armed, or None."""
    try:
        raw = json.loads(RTC_ARMED_FILE.read_text(encoding="utf-8"))
    except OSError, ValueError:
        return None
    epoch = raw.get("epoch") if isinstance(raw, dict) else None
    target = raw.get("target_date") if isinstance(raw, dict) else None
    if isinstance(epoch, bool) or not isinstance(epoch, int):
        return None
    return ArmedRecord(epoch, target if isinstance(target, str) else "")


def _write_record(record: ArmedRecord | None) -> None:
    """Persist (or, for None, delete) the record; failures only log."""
    try:
        if record is None:
            RTC_ARMED_FILE.unlink(missing_ok=True)
            return
        RTC_ARMED_FILE.parent.mkdir(parents=True, exist_ok=True)
        RTC_ARMED_FILE.write_text(
            json.dumps({"epoch": record.epoch, "target_date": record.target_date})
        )
    except OSError as exc:
        _logger.warning("Could not update %s: %s", RTC_ARMED_FILE, exc)


def arm(epoch: int, target_date: str) -> tuple[bool, str]:
    """Set the RTC alarm (unless it already is exactly this) and record it."""
    if current_alarm() == epoch:
        ok, detail = True, "already set"
    else:
        ok, detail = _rtcwake("-m", "no", "-t", str(epoch))
        detail = detail or "armed"
    if ok:
        _write_record(ArmedRecord(epoch, target_date))
    return ok, detail


def disarm_ours() -> tuple[ArmedRecord | None, bool, str]:
    """Clear the pending alarm only if it is the one we recorded.

    Returns:
        ``(record, disarmed, detail)``. ``record`` is None when we had armed
        nothing; ``disarmed`` is True only when ``rtcwake -m disable`` ran
        and succeeded. A record whose alarm is no longer pending (it fired,
        or someone else replaced it) is simply forgotten.
    """
    record = read_record()
    if record is None:
        return None, False, "nothing of ours armed"
    if current_alarm() != record.epoch:
        _write_record(None)
        return record, False, "no longer pending"
    ok, detail = _rtcwake("-m", "disable")
    if ok:
        _write_record(None)
    return record, ok, detail or "disarmed"
