# Migration: GitHub Gist → shared `crdt_sync`

`phone_app`'s alarm sync was moved off a bespoke GitHub Gist onto the shared
[`crdt_sync`](https://github.com/kuhyx/utils/tree/main/crdt_sync_dart) library
(pinned tag `crdt_sync_dart-v0.3.0`), matching how the other companion apps
sync.

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
