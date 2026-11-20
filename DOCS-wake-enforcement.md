# Wake enforcement v2 — PC fallback alarm, immediate stick, escape hatch

Agreed with kuhy on 2026-10-01. This file is the **contract** between the
phone app, the PC package, focus-owner (`~/src/phone-focus-mode`) and the
daily audit. Change a name here and in every reader in the same commit.

## Why

The carrot (`DOCS-morning-session-pc.md`) pulls only on days the PC is used
in the morning — Fri–Mon. On Tue/Wed/Thu kuhy leaves for work, so the only
lever is something that bites *today*. Two holes made skipping cheap:

1. **A phone switched off before the alarm escaped everything.**
   `RingWatch.markFired` never ran, so `WorkdayStick` saw no abandoned ring.
2. **Nothing rang if the phone was off.** The PC's waking role was deleted on
   2026-08-30; this brings back exactly one piece of it because the phone
   *cannot* ring while powered off — the reason AGENTS.md asks for.

## Behaviour

### PC fallback alarm (every ringing day)

Let `A` be today's alarm (`_sync.get_alarm()`, clamped ≤ 08:00 like the
trigger). Not on a free day, not on a sick day (below). Per-minute tick, `A-5min .. A+45min`:

| condition (first match wins) | action |
|---|---|
| escape recorded for today, or a session started today | stop / do not ring |
| ring already ran 30 min today (`FALLBACK_RING_CAP`) | never again today |
| `now ≥ A + 2 min` and no `ring_started` for today | ring — `phone_silent` |
| `now ≥ A + 15 min` (`SESSION_NONE_GRACE`) | ring — `no_session` |

A ring stops on: session start, escape, or the 30-min cap. Firebase
unreachable counts as "no ping, no session" (fail toward ringing) and is
logged as `firebase_unreachable`. While ringing, stop conditions are polled
every 20 s.

**A `no_session` ring after a phone ring is correct, not a missed read
(traced 2026-11-16).** On 2026-10-26 and 2026-11-01 the PC went
`waiting` → `no_session` at A+15. It never logged `phone_silent`, so it did
see `ring_started`. What it never saw was a session for today: the
session tick logged "Newest morning is 2026-10-25" and "2026-10-29" all
morning. Firebase agrees. On 11-01 the phone fired, opened the ring screen
at 07:43 and then logged nothing until a boot at 11:27: no `dismissed`
event, no session. On 10-26 the session started at 11:01. So the PC was
right on both days. A ringing phone that nobody dismisses is the case the
`no_session` row exists for. `test_fallback_policy.py`
(`test_ring_started_waits_for_the_session_grace`) pins it. Why the phone
went quiet after 07:43 on 11-01 is a separate phone question.

**Sound.** 100 %, unmuted, a tone that rises over the first 60 s.
- Active graphical session on seat0 → user PipeWire (`wpctl` + `pw-play`).
- Otherwise (night lockdown: lightdm masked, nobody logged in; kuhy is not in
  `audio`) → root system unit `wake-alarm-ring-alsa.service` playing straight
  to the speakers' card (`ALC897 Analog`, card name `Generic_1`) via `aplay`.

### PC wakes itself (nights before Tue/Wed/Thu)

`wake-alarm-rtc.timer` (evenings + on boot) arms the RTC for
`A − 10 min` of the next stick-day morning with
`sudo -n /usr/sbin/rtcwake -m no -t <epoch>` (already NOPASSWD). The alarm
lives in CMOS, so it survives however the PC goes down.

`~/.config/wake_alarm/pc_wake.json` `{"mode": "hibernate" | "poweroff"}`:
- `hibernate` (default): a logind drop-in makes the **power key** hibernate.
  Verified on the host 2026-10-01: two `rtcwake -m disk` cycles resumed
  29–44 s after the alarm (FADT: "RTC can wake system from S4 = 1").
  A typed `shutdown` stays a real poweroff.
- `poweroff`: no logind change; relies on the firmware waking from S5.
  vmbox only, 2026-11-15 (`vm new --uefi`, OVMF): `rtcwake -m no -s 120`
  then `systemctl poweroff` left AIE and `RTC_EN` set in CMOS, and the
  guest cold-booted 12 s (guest clock) after the alarm (`result=woke`).
  QEMU has no S5 wake path, so `vm wake` emulates the firmware half: this
  proves the arming survives a poweroff, not that this board wakes from S5.
  Host S5 firmware check dropped by kuhy 2026-11-15 (needs a physical
  power-on).

### Phone stick (Tue/Wed/Thu, not free days)

A **miss** = no dismiss by `A + 15 min` and no escape for today. Detected by
an exact alarm at `A + 15` *and* at boot (stored alarm `A` passed by ≥ 15 min,
not dismissed today) — the boot path is what closes hole 1.

Lockdown length stacks over **consecutive stick-day misses** (free days are
skipped, they neither break nor extend the streak; a dismissed or escaped
stick day resets it to 0):

| streak after this miss | locked through |
|---|---|
| 1 | today + 1 day |
| 2 | today + 2 days |
| n | today + min(n, 4) days (5 calendar days max) |

During a workday lockdown focus-owner applies its **lockdown allowlist**
(calls, SMS, Signal, maps, transit/ticket, banking + authenticator,
wake-alarm, todo) — narrower than the night list.

### Sick days (PC side, 2026-10-16)

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

### Escape hatch (until 2026-10-15 inclusive)

Bug-glyph button on the stakes card (spoken label "That was a bug"; the
app is text-free since 2026-11-10). Needs a typed reason ≥ 40 characters.
It lifts the phone lockdown, clears the streak, cancels today's PC penalty,
stops a ringing PC alarm, and writes everything into the incident report.
Unlimited uses — every use is listed at the top of that day's report.
After `escapeHatchLastDay` the button is gone (constant, not a setting).

### Stakes shown in the app

Home card: today's stakes (stick day or carrot day), the carrot cutoff, any
pending lockdown/penalty and the streak. Ring screen: one line. Every number
shown comes from Dart constants mirrored against the Python ones by
`wake_alarm/tests/test_stakes_mirrors.py`.

## Data contract

### Firebase — fields on the phone's `alarm.json` (`stageField`)

| field | value |
|---|---|
| `ring_started` | `{"date": "YYYY-MM-DD", "at": "<ISO-8601 with offset>"}` — set when the ring screen opens (Dart). |
| `escapes` | list, newest first, ≤ 30: `{"id", "date", "at", "reason"}` — `date` is the morning being excused. |
| `stick_state` | `{"streak": n, "locked_through": "YYYY-MM-DD" \| null, "last_miss": "YYYY-MM-DD" \| null}` |
| `phone_events` | list, newest first, ≤ 400 entries and ≤ 14 days: `{"at", "kind", "data": {…}}` |

### focus-owner broadcasts (signature permission `SIGNAL_LOCKDOWN`)

- `com.kuhy.focus_owner.action.LOCKDOWN_UNTIL_EOD` — extra `until`
  (`YYYY-MM-DD`, inclusive). Missing extra = today (old senders keep working).
- `com.kuhy.focus_owner.action.LIFT_LOCKDOWN` — clears any lockdown now.

### PC files (`~/.local/state/wake_alarm/`)

- `events.jsonl` — every PC event (`_log_sink`), `event` key names below.
- `fallback_ring.json` — today's latch: `{"date", "started_at", "stopped_at",
  "reason", "stop_reason"}`.
- `workday_penalty.json` — unchanged shape; not written for an escaped day
  or a sick day, and removed when an escape arrives for the day it was
  issued or that day is marked sick.

### Event names

Phone (`phone_events.kind`): `alarm_fired` (data: `reason` =
`daily`|`rering`|`free_day`|`sick_day` — only `daily` is the morning's ring),
`ring_screen_opened`, `ring_started_published` (data: `date`, `source` =
`alarm`|`ring_screen`), `dismissed`, `stick_check` (data: `trigger` =
`exact`|`boot`|`watchdog`, `date` judged, `verdict`, incl. `free_day`|`sick_day`), `lockdown_sent` (data:
`until`, `streak`), `lift_sent`, `escape_used`, `boot`.

`ring_started` is published twice over: a headless Dart engine started by
`AlarmReceiver` at the fire (so a full-screen intent downgraded to a heads-up
on an unlocked phone still counts) and the ring screen; first of the day wins.
The A+15 check uses `setExactAndAllowWhileIdle` (falls back to
`setAlarmClock` only when exact alarms are refused), so it never shows as the
system's next alarm. Boot/watchdog catch up on up to 5 unchecked past days.

PC (`events.jsonl` `event`): `fallback_tick` (only on decision change),
`fallback_ring_start`, `fallback_ring_stop`, `ring_backend`, `rtc_armed`,
`rtc_skip`, `firebase_unreachable`, `escape_seen`, `penalty_written`,
`penalty_cancelled` (field `cause`: `escape` | `sick_day`), `audit_written`.

## The desktop must come back after lockdown (2026-11-20)

The carrot assumes the PC has a desktop in the morning. On 2026-11-20 it did
not: the nightly `auto-system-update` installed NVIDIA 620.73 and kernel 7.3.5
while the PC sat in night lockdown. At 05:00 the unlock started lightdm, Xorg
died on `NVRM: API mismatch`, lightdm hit `start-limit-hit`, and every later
trigger logged "already UNLOCKED". kuhy saw only the text console.

The fix lives in digital-wellbeing (`lib/payloads/night-lockdown-gui-recover.sh`):
a morning trigger that finds state UNLOCKED with lightdm down starts it again,
after `reset-failed`. On a driver mismatch it reloads the NVIDIA modules. When
the running kernel has no modules left, it reboots once that day. Boot units
that raced DNS (`reflector`, `periodic-system-startup`) now retry
(system-maintenance). The cause of that race: testsAndMisc's Arch performance
fixers had disabled `NetworkManager-wait-online`, so `network-online.target`
was reached before the LAN existed; they now keep it enabled. Nothing in this repo changed: the morning session and
its 11:00 deferral were fine; only the desktop was missing.

## Verification status (2026-10-01)

- vmbox gate (`scripts/vmbox/harness.sh`, `guest_cases_v2.sh`): install,
  timers, root ring unit on `snd-dummy`, sudoers merge, power-key drop-in,
  a real `rtcwake` arm, uninstall — all pass. Passed in vmbox, then installed
  on the host.
- Host: S4 RTC wake verified twice; both ring backends start and stop. The
  root ALSA ring got `Device or resource busy` while PipeWire still held the
  card seconds after a PipeWire ring — at night the card is idle and opens
  (a silent root `aplay` passed), but a stream left open overnight would
  keep it busy. **Decided 2026-11-15:** on the *first* busy open (no retries)
  `ring_alsa.sh` rings through the user's PipeWire (`runuser`, then
  `python -m wake_alarm._ring_main`); only if that fails does it `fuser -k
  -TERM` the card's playback nodes once, retry ALSA once and exit non-zero.
  Fallback before kill, because the holder is PipeWire itself. The fallback's
  `ring_backend` event says `FAILED` (`started=false`) when PipeWire cannot
  play, and the unit's non-zero exit is the loud failure; the user-level
  fallback ring is the last line. Gate: vmbox `ring-alsa-busy-fallback`
  (10 repetitions) and `ring-alsa-busy-fails-loudly`.
- Emulator (`wake_alarm_api36`): exact A+15 check hidden from the system
  next-alarm, headless `ring_started` on a heads-up ring, boot-path miss
  (phone off before the alarm) → lockdown through tomorrow, escape hatch.
  Not yet on the Pixel: the real focus-owner reaction and Firebase publish.
- Item 13 (black screen): dropped by kuhy 2026-11-12
- Two-tag dismiss on device: dropped by kuhy 2026-11-12
- Locked-keyguard dismiss on device: dropped by kuhy 2026-11-12

## Evidence for Claude

`python -m wake_alarm._audit [YYYY-MM-DD] [--stdout | --force]` and the 11:05 timer write
`~/data/wake-alarm/incidents/<date>.md` (outside the repo: personal data): a merged
phone + PC timeline, then expected-vs-observed checks (alarm known, RTC armed, PC up
by `A`, ring/fallback, penalty, lockdown, phone pushed within `PHONE_PUSH_STALE_SECONDS`
= 24 h by newest dated HLC; n/a when Firebase is unreachable), mismatches and escapes first.
An existing report is never overwritten silently: exit 2 `refusing to overwrite <path>`
unless `--force`; `--stdout` (alias `--dry-run`) prints and writes nothing, not even
`audit_written`.
