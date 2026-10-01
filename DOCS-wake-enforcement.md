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
trigger). Not on a free day. Per-minute tick, `A-5min .. A+45min`:

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
  Unverified until the host S5 test runs.

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

### Escape hatch (until 2026-10-15 inclusive)

Home screen button "That was a bug". Needs a typed reason ≥ 40 characters.
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
- `workday_penalty.json` — unchanged shape; not written for an escaped day,
  and removed when an escape arrives for the day it was issued.

### Event names

Phone (`phone_events.kind`): `alarm_fired` (data: `reason` =
`daily`|`rering`|`free_day` — only `daily` is the morning's ring),
`ring_screen_opened`, `ring_started_published` (data: `date`, `source` =
`alarm`|`ring_screen`), `dismissed`, `stick_check` (data: `trigger` =
`exact`|`boot`|`watchdog`, `date` judged, `verdict`), `lockdown_sent` (data:
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
`penalty_cancelled`, `audit_written`.

## Evidence for Claude

`python -m wake_alarm._audit [YYYY-MM-DD]` and the 11:05 timer write
`~/data/wake-alarm/incidents/<date>.md`: a merged phone + PC timeline, then
expected-vs-observed checks (alarm known, RTC armed the night before, PC up
by `A`, ring/fallback, penalty, lockdown), mismatches and escape uses first.
Outside the repo on purpose: it holds personal data.
