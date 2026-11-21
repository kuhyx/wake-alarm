# Sick days -- PC side (2026-10-16)

Split out of `DOCS-wake-enforcement.md` (250-line gate). The phone half and
the pool itself: `DOCS-sick-days.md`.


A sick day (that does not keep `alarm`, see below) is a date in the shared `sickdays` pool (`~/src/utils/sickdays`):
uncapped, no reason, today or later, and **not a free day** -- its own pool,
its own reason strings (`sick_day` / `sick day`). On a sick day `D` (the
alarm's day, so the RTC asks about *tomorrow* the evening before):

| piece | on a sick day |
|---|---|
| fallback ring | never starts; a ring in progress stops (`stop_reason` `sick_day`) |
| RTC self-wake | not armed for `D`; an alarm we armed for `D` is disarmed (`rtc_skip` / `rtc_disarmed`, reason `sick day`) |
| trigger | `morning-routine.service` is not started (`sick day`), like a free day |
| workday penalty | never written for `D`; one *issued* on `D` before `D` was marked is deleted (`penalty_cancelled`, `cause: sick_day`) by the next `_session --refresh` or `_rtc --arm` |
| `morning_session.json` | unchanged: it only *grants* exemptions, and every locker stands down on a sick day by its own check |
| audit | RTC / up-by-A / ring / lockdown checks are n/a; a penalty for `D` on disk or a `lockdown_sent` for a miss on `D` is flagged |

All of it lives behind `wake_alarm/_sick.py`. **Fail closed:** an
unreadable pool, or `sickdays` not importable under `/usr/bin/python`, is
"not sick" -- enforcement runs.

**Sync.** The decisions read the local pool, and the act modes pull it from
Firebase first (`sickdays.sync_quietly()`), because the sickdays sync timer
alone cannot be trusted at the moment that matters: it is a monotonic
15-minute timer, paused during hibernate and with no `Persistent` catch-up,
so right after the RTC resume the pool can be an interval stale. Pulled:
`_rtc --arm` when the target is a stick day that is not free; the fallback
tick whenever it already goes to the network (`A-5 .. A+45`, and every poll
of a ring in progress, so a day marked sick mid-ring stops it); the day's
first penalty write. The trigger reads only the local file -- the fallback
has pulled from `A-5`. `--dry-run` / `--show` never pull (a pull rewrites
the pool file).

**Other readers of `workday_penalty.json`** (screen-locker, leetcode-guard)
must treat the file as void when **either** its `issued_date` is a day the
*alarm* stands down on (`sickdays.stands_down(sickdays.LOCKER_ALARM,
date.fromisoformat(issued_date))`) **or** its `penalty_date` is a day *their
own* locker stands down on (`stands_down(LOCKER_WORKOUT, ...)` for
screen-locker, `LOCKER_LEETCODE` for leetcode-guard). `issued_date` covers a
miss at 08:15 marked sick at 14:00 -- the deletion runs on the next RTC tick
(<= 15 min) or the next morning's refresh, and a reader must not depend on
that; the ring day belongs to the alarm switch, the penalty day to whatever
the penalty charges.

**Keeping the alarm (`sickdays` 0.2.0).** A sick day may keep lockers
(`sickdays add --keep alarm`). Everything in the table above is the single
`alarm` switch (`_sick.alarm_stands_down`): on a sick day that keeps `alarm`
the fallback ring, RTC self-wake, trigger, workday penalty (written, and not
retracted) and audit behave exactly as on a normal stick day.

**Phone, assumed name:** the phone's `alarm_fired` on a sick day carries
`data.reason = "sick_day"` (by analogy with `free_day`); the audit treats
it as not the morning's ring.

**A stand-down latches at ring time (fixed 2026-11-16).** On 2026-11-11 the
07:40 ring stood down for a sick day (`alarm_fired reason=sick_day`), the
phone cleared the mark at 11:38, and the 19:31 stick check re-read the cache,
found a normal Wednesday with no dismissal and sent a lockdown. That punished
a day whose alarm never rang, so no dismiss was possible. `AlarmReceiver` now
records the skip (`RingWatch.markSkipped`, a `DateHistory` per reason), and
`StickCheck.decideDay` returns `sick_day`/`free_day` for a latched day even
after a clear. The streak look-back skips it too. A phone that was off at A
latches nothing, so a clear still makes that day a stick day (hole 1).
Tests: `StickCheckSickTest`.

**Still open: on-device check.** At the next real miss (Tue/Wed/Thu), right
after 09:30 run `adb -s 23181JEGR08034 logcat -d | grep -E
"LOCKDOWN_ACTIVATED|WORKDAY_LOCKDOWN"` (read-only) and confirm
`LOCKDOWN_ACTIVATED` is followed by `WORKDAY_LOCKDOWN`.
