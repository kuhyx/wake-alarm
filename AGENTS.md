# CLAUDE.md — wake_alarm

## What this does

**The phone is the alarm.** `phone_app/` arms and rings it and gates the
dismissal; this repo's Python half only reads the alarm time the phone
published and starts the morning routine at that time. The time is an earned
ramp, 08:00 down to 07:00, owned by the phone alone — **`DOCS-ramp.md`**.

The PC's waking role was deleted on 2026-08-30: no alarm window, no smart
plug, no curtains, no `shutdown` wrapper, no sleep hook. On 2026-10-01 exactly
two pieces came back, because the phone **cannot** ring while powered off: a
**fallback ring** when the phone is silent or no session started, and an
**RTC self-wake** before Tue/Wed/Thu. Plus the stacking phone lockdown and a
temporary escape hatch (until 2026-10-15). All of it, and the data contract
the phone, PC and focus-owner share: **`DOCS-wake-enforcement.md`**. Anything
else from the old PC alarm still needs a reason the phone can't do it.

## The dismiss sequence (phone)

```
tag 1  ->  25 steps + 2 min  ->  tag 2  ->  3 challenges
```

Owned by `phone_app/lib/services/dismiss_gate.dart`. **Strict order, and every
stage latches** — an unknown or out-of-order tag is ignored, never a reset.
`room_proof.dart` answers only "did this one check pass just now"; the
ordering lives in the gate. Keep it that way: the previous version smeared the
decision across `setState` calls and had a real bug where a wrong tap after
passing sent the user back to the start.

- **Two *distinct* tags.** The same id in both slots is refused at
  registration — one tag satisfying both stages removes the walk, which is the
  entire point. Stored as a JSON list under `roomProof.nfcTagIds`; a legacy
  single `roomProof.nfcTagId` migrates into slot 1. **Tags and home location
  sync** (`settings_sync.dart`, see `DOCS-phone-alarm.md`) — a reinstall
  gets them back; do not make either local-only again.
- **Steps** (`requiredSteps = 25`) are counted from ring start, *not*
  re-baselined at tag 1, so walking to tag 1 already banks them and the stage
  passes on its first poll. The 2-minute elapsed floor (`requiredElapsed`)
  applies **only under bypass/away**, where no tag proved the walk and a
  shaken phone would count; on the normal path it was two minutes of ringing
  nothing could shorten (dropped 2026-09-16).
- **Answers are cumulative, not consecutive.** A wrong one costs the attempt
  and nothing else.
- **The bypass skips the tags, never the walk.** After
  `DismissGate.bypassAfter` (5 min), or immediately when NFC is off or fewer
  than two distinct tags are registered, the tag stages are skipped and the
  count rises to 6. Jumping straight to the challenges would let someone lie in
  bed for five minutes and answer questions without standing up — weaker than
  the gate this replaced. Do not "simplify" it into that.
- **No challenge may hide its prompt.** The memorise-then-hide kind was
  deleted, not merely unrouted: the ring screen is reached by walking in from
  another room.

**The dismiss does not end the morning.** Since 2026-09-16 it hands over, in
the same activity, to the silent **morning session**: weigh in → bathroom tag
→ shower → bathroom tag again → wardrobe tag → desk tag. A missed window
(AlarmManager, request code 1003) re-rings; silencing it is the full sequence
again; three re-rings fail the session. Leaving the app is fine: every launch
while the morning is live lands back on the leg (`SessionNotice.kt`). State is
persisted after every change, on wall-clock instants: **`DOCS-morning-session.md`**.

**`HomeScreen.initState` must stay strictly sequential** (`_applyPolicy` →
`_loadSyncState` → `_syncToPc`): run concurrently, the startup publish
captured a null store and **nothing published for three weeks**. Why, the
two deliberately distinct `publish()` failure strings, the ring's injectable
clock, and everything that is a hard crash or a silent no-ring:
**`DOCS-phone-alarm.md`**.

**Free days.** On a day in the shared pool (`~/src/utils/freedays`) the phone
does not ring at all: `AlarmReceiver` checks a native cache Dart rewrites
after every mark/release/sync. Picker, cache and its fail-closed contract:
**`DOCS-free-days.md`**.

## Scheduling — a per-minute timer

`wake-alarm-trigger.timer` ticks every minute (`OnCalendar=*:*:00`,
`Persistent=true`) and runs `python -m wake_alarm._trigger` — a short,
stateless check-and-fire. It resolves the alarm via `_sync.get_alarm()`, builds
today's fire instant in **local** time, and fires iff `now` is in
`[fire_time, fire_time + TRIGGER_CATCHUP_MINUTES)`. Firing means
`systemctl --user start morning-routine.service`, which runs the workout lock.

**The once-per-day latch is load-bearing.** After a successful start,
`_trigger` writes `save_trigger_fired()` and `_skip_reason` gates on
`was_trigger_fired_today()`. Without it the routine restarts on every tick for
the rest of the 60-minute window: the unit is `Type=simple`, so a start while
it runs is a no-op, but the moment the workout lock finishes the next tick
relaunches it on top of the user. This latch replaced the alarm's own
dismissal record when `_alarm.py` was deleted — deleting one without adding the
other is a silent regression, and that is exactly the trap.

`Persistent=true` plus the 60-minute window is also what replaced the deleted
systemd-sleep hook: a suspended or just-booted machine still fires.

## Reading the phone's alarm

`_sync.py` is the only reader.

- Source of truth: a `crdt_sync` log written by `phone_app/` under
  `wake-alarm-sync/devices/<device-id>/alarm.json`, at
  `.alarm.fields.alarm_hour[0]` / `.alarm_minute[0]`. Same logical path on both
  backends, so only the transport differs, never the parse.
- **The Firebase reader discovers device directories; it is not pinned to
  `devices/phone/`.** The phone's device id is migrating from the fixed
  constant `phone` to a per-install uuid, and a pinned reader would silently
  stop seeing the alarm and fall back to 08:00 — i.e. the wrong
  time. `_fetch_firebase_alarm()` lists `SYNC_DEVICES_PREFIX`, reads every
  device's `alarm.json`, and picks the newest by the hour field's **HLC**, with
  `device_id` breaking exact ties. A payload that does not parse is skipped
  rather than allowed to win. `SYNC_ALARM_PATH` remains as a last-resort read
  for a backend that lists nothing.
- Payload parsing/ranking lives in `_alarm_payload.py`: `_sync.py` owns
  fetching, caching and fallback; `_alarm_payload.py` owns "what did the phone
  actually say".
- **Firebase first, GitHub as the cutover mirror.** Retiring the mirror is
  deleting the GitHub branch plus `SYNC_API_BASE`/`SYNC_REPO_*`.
- Firebase config: shared `~/.config/crdt-sync/firebase.json`; the refresh
  token is cached per app under `SYNC_APP_NAME` (`wake_alarm`). The config file
  is checked **before** anything is constructed, so an unconfigured machine
  never touches the network.
- GitHub token (fallback only): `~/.config/wake_alarm/sync.json` key `token`,
  else a sibling app's raw `~/.config/{diet_guard,screen_locker}/sync_token`.
  Needs `repo` scope — the repo is private, so a token without access returns
  **404, not 403**.
- `crdt_sync` is imported at module scope but **guarded by
  `try/except ImportError`**: the service runs `/usr/bin/python`, not a venv, so
  a dependency that failed to install must degrade the read to the GitHub path
  rather than crash the per-minute trigger. The GitHub path stays stdlib-only
  for that reason. Verify with `/usr/bin/python3 -c "import crdt_sync"`, not the
  dev venv.
- Resolution chain in `get_alarm()`: fresh cache (< 5 min) → live fetch → stale
  cache → 08:00. The cache bounds remote reads to ~288/day
  despite the per-minute tick.
- **A record older than `PUBLISHED_ALARM_MAX_AGE_SECONDS` (14 days) is skipped
  at every step, including the cache.** The check is on when the *phone
  stamped it*, never on when we fetched — checking the fetch is trivially
  defeated, because the cache is rewritten from the same stale record every few
  minutes, so `fetched_at` is always fresh however old the record behind it is.
  That is why the winning HLC's instant is carried through `_alarm_payload` →
  `_sync_transport` → the cache's `published_at`. Expiring is safe because
  08:00 is the latest the phone can ever arm. An **undated** record is
  trusted, not expired: the GitHub mirror has no per-field HLC, so treating
  "cannot tell" as "too old" would break that backend entirely.
- **Degraded reads log at INFO, not WARNING.** `get_alarm()` runs every minute;
  a persistent condition logged loudly is 1440 journal lines a day. `_trigger`
  emits the single WARNING that matters: firing *now* on a non-phone time.
- **The morning session is the carrot** (`_session.py`, `wake-alarm-session.timer`,
  **`DOCS-morning-session-pc.md`**): a completed-in-time morning defers the
  workout and LeetCode locks to 11:00 via one signed file both consumers read.
  Phone-local dates only — never `_state._today_str()` (UTC).

## The morning_routine orchestrator lives elsewhere

`morning_routine._orchestrator` (in `testsAndMisc/python_pkg/morning_routine/`)
is what `_trigger` starts, and it now runs one leg: `screen_locker.screen_lock`.
Its alarm leg was removed in the same change that deleted `_alarm.py`.

**When this package's module paths change, the orchestrator must change in the
same commit.** Leaving it pointing at a module that no longer exists caused a
month-long silent production failure once already (2026-05-28, orchestrator
still on `python_pkg.screen_locker.screen_lock` after screen-locker's
extraction): the alarm fired and dismissed correctly while the workout lock
crashed with `ModuleNotFoundError` on every run.

## Production dependency installation

`wake-alarm-trigger.service` runs `/usr/bin/python` directly — **not** a venv.
Any new non-stdlib dependency must go into system Python's *user*
site-packages:

```bash
/usr/bin/python3 -m pip install --user --break-system-packages -e .
```

**Run `install.sh` (or `pip install -e`) from a durable clone**, not a scratch
directory — it is editable, so a later `git pull` in that clone updates the
running production code. From `/tmp` or via `pip install "wake_alarm @ git+..."`
you get a snapshot frozen at that commit, and the next push silently does not
reach the running service. Convention: `~/src/wake-alarm`, mirroring
`~/src/screen-locker`.

If you add a dependency and only install it into a dev venv, the service fails
with `ModuleNotFoundError` on its next run — this exact gap caused a 3-day
diet_guard outage. Verify against `/usr/bin/python3 -c "import <dep>"`.

## Uninstalling

`uninstall.sh`, never `rm -rf` on the repo: it also removes the root ring
unit, the logind power-key drop-in and an RTC alarm we armed, and retires the
old `/usr/local/bin/shutdown` wrapper wherever one survives. `install.sh` calls `uninstall.sh --retired-only` as its last step, so
**`uninstall.sh` is load-bearing for installing**, not just for removing —
renaming or deleting it breaks a fresh install. That call is non-fatal and
gated on `sudo -n`: the cleanup needs root, and a hard failure there would
abort an install that had already placed the package and enabled the timer.

**`/etc/sudoers.d/wake-alarm` is deliberately left in place** even by a full
uninstall. Since 2026-10-01 it is live again: the RTC self-wake's `rtcwake`
and the root ring unit's `systemctl start|stop` lines live there.

## Operational gotchas

- **`wake_state.json` is runtime state, not tracked.** It holds the
  HMAC-signed once-per-day latch. It was accidentally committed in the
  monorepo and must stay gitignored here.
- **`WAKE_STATE_FILE` is redirected in `tests/conftest.py`, not per-file.**
  `_trigger` writes it now, and the trigger tests never redirected it — a
  per-file redirect is exactly the kind that gets forgotten when a new writer
  appears, and the failure is silent: a green suite that quietly stamped the
  live state file.

## Commands

- Run tests: `python -m pytest wake_alarm/tests/ --cov=wake_alarm --cov-branch --cov-fail-under=100`
- Phone tests: `cd phone_app && flutter test && flutter analyze`
- Walk the morning on the emulator: `phone_app/scripts/emu_morning.py` (`DOCS-morning-session.md`)
- Lint: `pre-commit run --all-files`
- Show the resolved alarm / the morning: `python -m wake_alarm._sync --show` (`--no-cache` live), `python -m wake_alarm._session --show`
- Show what the next tick would do: `python -m wake_alarm._trigger --dry-run`
- Watch it live: `journalctl --user -fu wake-alarm-trigger.service`
- Install: `bash install.sh` — Uninstall: `bash uninstall.sh`
- Gate the shell/system scripts: `bash scripts/vmbox/harness.sh`
  (disposable Arch VM; see **`DOCS-vmbox.md`**)
- Ring the phone for a manual test: `lib/main_ring_probe.dart` (see
  `DOCS-phone-alarm.md` — it starts a **real** alarm, and the new sequence is
  what stops it)

The dev venv lacks `gatelock`, so anything importing `_state` (including
`_trigger`) needs `/usr/bin/python3`, not `.venv/bin/python`.

## Do NOT

- Don't add a dependency without the production install-path check above.
  `_sync.py`'s GitHub path is stdlib-only for that reason — don't "improve" it
  to `requests`, and don't make the `crdt_sync` import unconditional. Don't
  forget the orchestrator when changing this package's module paths.
- Don't point the trigger at anything but `morning-routine.service` (or the
  workout lock never runs), don't remove its once-per-day latch, and don't
  raise the log level of `_sync`'s degraded-read paths.
- Don't let the bypass skip the walk, and don't add a challenge kind that
  hides its own prompt.
- Don't close the ring screen on dismiss when a session should follow, don't
  add a re-ring cancel beyond the session's own `finishSession`, and don't
  restore a re-ring instant that has passed (BOOT_COMPLETED replays on launch).
- Don't make `HomeScreen.initState` concurrent again; keep `publish()`'s two failure messages.
- Don't date a record by when the PC fetched it, and don't let a consumer of
  `morning_session.json` re-derive the 09:30/11:00 cutoffs or fetch its own copy.
- Don't delete `/etc/sudoers.d/wake-alarm`. Don't commit `wake_state.json`.
