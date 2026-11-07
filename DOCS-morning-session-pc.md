# The morning session on the PC — the carrot, and what it costs to skip

Companion to `DOCS-morning-session.md` (the phone side). This is how the
phone's morning turns into "no workout lock, no LeetCode lock" on the PC, and
why an aborted morning turns into neither.

## Why

On 2026-09-19 the alarm rang, the full dismiss ran, the session reached the
bathroom tag — and the phone was powered off. Nothing on the PC noticed: the
phone was publishing every finished session and nothing read it, the
workout-lock "carrot" was a hardcoded 05:00–08:30 window in screen-locker
with no link to getting up, and leetcode-guard locked at login regardless. So
finishing the morning was worth at most 30 minutes, and aborting it cost
nothing. Powering the phone off cannot be prevented (device-owner
provisioning, and a 10 s hardware off still wins); it can be *noticed*.

## The rule

The goal is *waking up*, not reaching a clock. So the PC is open from the
moment it is usable (the night lockdown lifts at 05:00) until the alarm has
rung and been dismissed; the dismiss plus the morning session is the "are
you still up" check, and passing it keeps the PC open until 11:00
(2026-09-20 — the first version only opened at 08:30 and locked someone who
got up at 07:00, the opposite of the point):

| the phone says | `exempt_until` | meaning |
|---|---|---|
| nothing started today (`none`) | **alarm + 15 min** (`SESSION_NONE_GRACE`; alarm = the phone's, clamped to ≤ 08:00 like the trigger) | up early is fine; the phone rings at the alarm, and a dismiss that has not produced a session by then means "not up" |
| started, not finished (`in_progress`) | `min(started_at + 90 min, 09:30)` | provisional — the legs take ~40 min; relative to the start because an alarm earlier than 08:00 is legal and a fixed 09:30 would hand an aborted 06:15 session three hours |
| `completed`, finished inside that same cutoff | **11:00** | the carrot |
| `completed` *after* the cutoff | none | a phone switched back on at noon completes the legs then; that un-locks nothing |
| `failed` | none | today's ordinary ladder |
| alarm unknown (unconfigured PC) | none | fail closed |

Fail closed: a sync outage, a refresher that is not running, a bad signature
— all read as "no carrot". Nothing here can make a lock *earlier* than today.

## The plumbing

**wake-alarm is the only Firebase reader.** `wake-alarm-session.timer`
(`*-*-* 05..06:00/10:00`, `07..10:00/2:00` and `11:00:00`, `Persistent=true`,
~133 reads/day — from 05:00 because that is when the login-armed locks
decide) runs `python -m wake_alarm._session --refresh`:

1. `_sync_transport.fetch_firebase_logs()` — every device's `alarm.json`.
2. `_session_payload.newest_session()` — the finished entries of
   `morning_sessions` plus `current_session` when it is live, ranked by
   `(date, finished-before-live, HLC, device_id)`. **By content, never by
   comparing the two fields' stamps**: a phone that lost the network at
   finish and never cleared `current_session` still resolves to the finished
   morning. The phone's `active` becomes `in_progress`.
3. `_session.to_entry()` + `write_entry()` — an HMAC-signed
   `~/.local/state/wake_alarm/morning_session.json` that **always describes
   today** (PC-local date): today's session with `exempt_until` signed in, or
   a `none` entry (exempt until alarm + 15 min) when the phone has nothing
   for today. The entry is also what lets a consumer tell "fresh, no session"
   from "the refresher has not run yet" by the date alone.

Dates are the phone's local day throughout. `wake_alarm._state._today_str`
is UTC and must not be used here (screen-locker compares against its local
`today_str`; a UTC date would miss by a day every evening).

**Consumers apply one predicate**: signature verifies ∧ `date == local today`
∧ `exempt_until` present ∧ `now < exempt_until`. Neither re-derives the
cutoffs, neither imports `crdt_sync`, neither talks to Firebase:

- screen-locker `screen_locker/_morning_session.py` → **the early-bird
  window *is* this carrot** (`EarlyBirdMixin._is_early_bird_time`, since
  2026-09-20; the 05:00–08:30 clock and the extended-to-09:00 reward are
  gone). The `wake_alarm_skip` rung defers and banks the early-bird marker;
  when the carrot ends, the next run tries a phone/RunnerUp workout before
  locking (`early-bird-workout-check.timer` at 09:30:30 and 11:00:30). The
  decision record carries `exempt_until` and `outcome`.
- leetcode-guard `leetcode_guard/_morning_session.py` → `_cli._run_lock`
  returns `EXIT_OK` with `deferred: …` before `build_client()`. A run
  deferral, never ledger state (`decide()` stays pure; a deleted file cannot
  mint an unlocked day). `leetcode-guard.timer` gained 09:30 and 11:00 slots
  so a deferred run is re-decided at both boundaries. `--check` prints a
  `morning` line.

**A PC booted mid-morning** has a missing or yesterday's file until the
timer's `Persistent=true` catch-up lands, and that needs the network. Only
the enforce path, only inside 05:00–11:00, and only when the file is not
today's, both consumers retry for ≤ 180 s (5 s steps) and then proceed as
normal with a WARNING. Status paths never wait; tests pin the retry to 0.
The refresher itself retries an unreadable backend every 5 s for 150 s
(`REFRESH_RETRY_SECONDS`) before exiting 1 with a WARNING: a PC booted at
07:48 had no DNS for its first seconds, and the old single try left the next
chance at the 07:50 tick (2026-11-07).

**`next_step`** (signed with the rest): while the session is `in_progress`,
the label of the first leg not in the phone's `passed` map, else `null`.
Names and labels live in `_session_legs.py` and are pinned to the phone's
`SessionLeg` by `wake_alarm/tests/fixtures/session_legs.json`, asserted by a
Python and a Dart test.

## Known limits (v1, deliberate)

- A lock already on screen is not lifted by a later publish: a session
  that completes at 09:45 after the 09:30 lock stays locked. The publish
  would have to arrive before the boundary. (The 05:00 login-arm no longer
  hits this: the day starts exempt.)
- A session finishing inside ~2 min before 09:30 may be seen as
  `in_progress` at the 09:30 tick and lock; bounded by the timer cadence.

## The workday stick (2026-09-23)

The carrot above only pulls on a day the PC is actually being used to enjoy
it — a weekend. On a workday the user leaves for the office regardless, so
losing/keeping the PC's lock was worth nothing, and powering the phone off
at ring time (which stops the alarm dead — nothing left to sync, no session
ever recorded) cost nothing either.

On **Tuesday/Wednesday/Thursday** — `wake_alarm._constants.STICK_DAYS`, the
same weekdays screen-locker already calls "relaxed"
(`_weekly_check.is_relaxed_day`) and leetcode-guard already prices as cheap
(`Pricing.doubled_days`) — a genuine miss (`failed`, or `none` past its own
`SESSION_NONE_GRACE`; a *late* `completed` is not a miss, the walk still
happened) costs tomorrow's leniency in both apps instead of just resetting
to normal. `wake_alarm._workday_penalty.maybe_apply()` runs at the end of
every `_session.refresh()` and, when a stick-day miss is detected and today
is not a free day, signs and writes
`~/.local/state/wake_alarm/workday_penalty.json` (`{"penalty_date":
"<tomorrow>", "issued_date": "<today>"}`) — deliberately a separate file
from `morning_session.json`, since that one always describes *today* and is
overwritten at the date rollover, so it cannot carry a marker forward.
screen-locker and leetcode-guard each read it with the same HMAC + date
predicate they already use for `morning_session.json`.

A phone-side stick (locking down distracting apps on the phone itself,
signalled to `phone-focus-mode`'s `focus-owner`) is the other half of this
and lives in `phone_app/`, not here — see its own commit/doc for the exact
signal shape.

## Commands

```sh
python -m wake_alarm._session --refresh   # fetch, select, rewrite the file
python -m wake_alarm._session --show      # the verified file + a verdict line
python -m wake_alarm._energy              # {"date", "level"} or exit 1
systemctl --user list-timers | grep wake-alarm-session
journalctl --user -u wake-alarm-session.service -n 20
leetcode-guard --check                    # the "morning" line
```
