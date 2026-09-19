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

A morning earns the carrot **only by being completed in time**:

| the phone says | `exempt_until` | meaning |
|---|---|---|
| started, not finished (`in_progress`) | `min(started_at + 90 min, 09:30)` | provisional — the legs take ~40 min; relative to the start because an alarm earlier than 08:00 is legal and a fixed 09:30 would hand an aborted 06:15 session three hours |
| `completed`, finished inside that same cutoff | **11:00** | the carrot |
| `completed` *after* the cutoff | none | a phone switched back on at noon completes the legs then; that un-locks nothing |
| `failed`, or nothing started today | none | today's ordinary ladder (screen-locker's 05:00–08:30 window, leetcode-guard at login/09:00) |

Fail closed: a sync outage, a refresher that is not running, a bad signature
— all read as "no carrot". Nothing here can make a lock *earlier* than today.

## The plumbing

**wake-alarm is the only Firebase reader.** `wake-alarm-session.timer`
(`*-*-* 07..10:00/2:00` and `11:00:00`, `Persistent=true`, ~121 reads/day)
runs `python -m wake_alarm._session --refresh`:

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
   a `none` heartbeat when the phone has nothing for today. The heartbeat is
   what lets a consumer tell "fresh, no session" from "the refresher has not
   run yet" by the date alone.

Dates are the phone's local day throughout. `wake_alarm._state._today_str`
is UTC and must not be used here (screen-locker compares against its local
`today_str`; a UTC date would miss by a day every evening).

**Consumers apply one predicate**: signature verifies ∧ `date == local today`
∧ `exempt_until` present ∧ `now < exempt_until`. Neither re-derives the
cutoffs, neither imports `crdt_sync`, neither talks to Firebase:

- screen-locker `screen_locker/_morning_session.py` → the `wake_alarm_skip`
  rung of `_auto_upgrade._check_today_state_exits`, in its old position
  (after `workout_logged_today`, before `early_bird_banked`). The decision
  record carries `exempt_until` and `outcome`.
- leetcode-guard `leetcode_guard/_morning_session.py` → `_cli._run_lock`
  returns `EXIT_OK` with `deferred: …` before `build_client()`. A run
  deferral, never ledger state (`decide()` stays pure; a deleted file cannot
  mint an unlocked day). `leetcode-guard.timer` gained 09:30 and 11:00 slots
  so a deferred run is re-decided at both boundaries. `--check` prints a
  `morning` line.

**A PC booted mid-morning** has a missing or yesterday's file until the
timer's `Persistent=true` catch-up lands, and that needs the network. Only
the enforce path, only inside 07:00–11:00, and only when the file is not
today's, both consumers retry for ≤ 30 s (5 s steps) and then proceed as
normal with a WARNING. Status paths never wait; tests pin the retry to 0.

## Known limits (v1, deliberate)

- A lock already on screen is not lifted by a later publish: a session
  that completes at 09:45 after the 09:30 lock stays locked. The publish
  would have to arrive before the boundary.
- A session finishing inside ~2 min before 09:30 may be seen as
  `in_progress` at the 09:30 tick and lock; bounded by the timer cadence.
- No extra stick for a `failed` session beyond losing the carrot.

## Commands

```sh
python -m wake_alarm._session --refresh   # fetch, select, rewrite the file
python -m wake_alarm._session --show      # the verified file + a verdict line
python -m wake_alarm._energy              # {"date", "level"} or exit 1
systemctl --user list-timers | grep wake-alarm-session
journalctl --user -u wake-alarm-session.service -n 20
leetcode-guard --check                    # the "morning" line
```
