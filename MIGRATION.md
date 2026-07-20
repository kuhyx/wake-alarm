# Migration: GitHub Gist → shared `crdt_sync`

`phone_app`'s alarm sync was moved off a bespoke GitHub Gist onto the shared
[`crdt_sync`](https://github.com/kuhyx/utils/tree/main/crdt_sync_dart) library
(pinned tag `crdt_sync_dart-v0.2.0` — see `phone_app/pubspec.yaml`, which is
the authority; `pubspec.lock` resolves it to `5be99ab`), matching how the other
companion apps sync. A `crdt_sync_dart-v0.3.0` tag also exists upstream and is
*not* in use here — bumping to it is an untaken decision, not a drift to fix.

## What changed

- **phone_app (Dart):** `gist_service.dart` is gone. `AlarmSyncService` stores
  the alarm locally in a `crdt_sync` `LogStore` (one HLC-stamped `Record`) and
  pushes it to `wake-alarm-sync/devices/phone/alarm.json` in `kuhyx/syncs` via
  `crdt_sync`'s `GitHubClient`. The device-flow OAuth scope moved `gist` →
  `repo` (the Contents API needs private-repo access).
- **shutdown-wrapper.sh (PC, Bash):** now reads that alarm from the Contents
  API (`Accept: application/vnd.github.raw`, so no base64) and parses the
  `crdt_sync` `Record` log with `jq` (`.alarm.fields.alarm_hour[0]`). Config
  moved from `~/.config/wake_alarm/gist_sync.json` `{token, gist_id}` to
  `~/.config/wake_alarm/sync.json` `{token}` (repo-scoped).

## Setup after pulling this

1. On the phone: Settings → **Connect GitHub** (now requests `repo` scope; the
   old gist-scoped token won't reach the Contents API).
2. On the PC: `~/.config/wake_alarm/sync.json` → `{ "token": "<repo-scoped>" }`,
   then re-run `install.sh` so `/usr/local/bin/shutdown` picks up the new
   reader.

## Surprises / non-obvious decisions

- **The consumer is a Python-less Bash reader** (`shutdown-wrapper.sh` runs at
  shutdown, when a Python runtime may not be available), so it can't use the
  `crdt_sync` library — it parses the log with `jq`. What makes that tractable:
  `Hlc.toStr()` is **lexicographically sortable == chronological**, so
  "latest wins" across device dirs is a plain string max, no date math.
- **The phone is push-only** (sole writer); there is no pull/merge. Its local
  `LogStore` is always the source of truth.
- Any parse miss still falls back to `WAKE_AFTER_HOURS`, so a bad read can
  never brick the morning wake.

# Migration: hibernate-scheduled → per-minute trigger timer

The PC is no longer shut down at night, which broke the whole scheduling
model: the wake time used to be decided once, at hibernate, and baked into the
RTC. With no shutdown there is no resume, so nothing fired the alarm at all —
and `wake-alarm.service` was `WantedBy=graphical-session.target`, so on an
always-on machine it fired at *login* time instead (`_should_run_alarm()` has
no time gate).

## What changed

- **New `wake-alarm-trigger.timer`** ticks every minute and runs
  `wake_alarm._trigger`, which fires `morning-routine.service` when the
  current local time is inside
  `[phone alarm, phone alarm + TRIGGER_CATCHUP_MINUTES)`. This is now the
  primary path; the phone can move the alarm at any hour and the PC follows.
- **New `wake_alarm/_sync.py`** — a Python reader for the same alarm file
  `shutdown-wrapper.sh` parses with `jq`, plus an on-disk cache
  (`~/.config/wake_alarm/alarm_cache.json`).
- **`wake-alarm.service` lost its `[Install]` section** and is no longer
  enabled; `install.sh` disables it to clear stale symlinks.
- **Token resolution gained a fallback** to the sibling apps'
  `~/.config/{diet_guard,screen_locker}/sync_token`, in both readers.
- `shutdown-wrapper.sh` and `sleep-hook.sh` keep working unchanged, now as the
  PC-is-powered-down fallback rather than the main mechanism.

## Surprises / non-obvious decisions

- **A timer, not a resident scheduler.** Each tick is a fresh process, so
  there is no daemon to die silently and no wall-clock jump to reason about
  across suspend/resume. `Persistent=true` plus the catch-up window is what
  makes a suspended PC still fire on resume.
- **Per-minute ticks, but a 5-minute cache.** Ticking every 5 minutes would
  also quantise *firing* to 5 minutes (07:03 → 07:05). Ticking every minute
  and only hitting the network when the cache is stale gives exact-minute
  firing at ~288 GitHub reads/day.
- **Degraded reads log at INFO.** At one tick a minute, a WARNING on a
  persistent condition is 1440 journal lines a day. The single WARNING that
  survives is `_trigger`'s "firing now on a degraded source".
- **The sync had been dead since the crdt_sync migration.** `wake-alarm-sync/`
  did not exist in `kuhyx/syncs` at all — the phone had never successfully
  pushed, and `~/.config/wake_alarm/sync.json` was never created, so the
  hibernate path had been silently using the `+8h` fallback. The phone app
  needs one successful "Set Alarm & Sync" to create that path.
- **Still open:** alarms edited directly in the Android Clock app do not reach
  the sync. Closing that needs an `ACTION_NEXT_ALARM_CLOCK_CHANGED` receiver
  in the phone app — planned, not yet built.
