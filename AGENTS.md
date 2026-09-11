# CLAUDE.md — wake_alarm

## What this does

**The phone is the alarm.** `phone_app/` arms and rings it and gates the
dismissal; this repo's Python half only reads the alarm time the phone
published and starts the morning routine at that time.

The PC's waking role was deleted on 2026-08-30: no alarm window, no audio
escalation, no smart plug, no curtains, no `rtcwake`, no `shutdown` wrapper,
no sleep hook. Making the PC wake someone reliably cost more than it returned.
Everything about it is in git history; do not reintroduce a piece of it
without saying why the phone cannot do that job.

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
- **Steps are unchanged** (`requiredSteps = 25`, `requiredElapsed = 2 min`),
  and are counted from ring start, *not* re-baselined at tag 1. Consequence:
  walking to tag 1 already banks the steps, so only the elapsed floor really
  binds — which is why the steps stage auto-polls instead of offering a button.
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

**`HomeScreen.initState` must stay strictly sequential.** It runs
`_applyPolicy()` → `_loadSyncState()` → `_syncToPc()` through one
`_bootstrapSync()`, because the last reads what the first two write and
`AlarmPublisher.publish` takes the service as a *parameter* — captured by
value, so a later assignment can never reach it. Running them concurrently
(as they once were) meant the startup publish always passed `null`, and since
that was the only publish site, **nothing published for three weeks** while
the PC honoured a record from 2026-08-09. `_pickEarlier` must publish too, or
the one schedule edit the app offers never reaches the PC.

Relatedly: `publish()` reports a missing *backend* and a missing *store*
differently on purpose. One string for both is what made the above look like a
configuration the user had never done, while Firebase was connected the whole
time.

`RingScreen` takes an injectable `clock`. `Stopwatch` reads the wall clock,
which `tester.pump()` does not advance, so without that seam no widget test
can reach the two-minute floor or the five-minute bypass.

More, including everything that is a hard crash or a silent no-ring:
**`DOCS-phone-alarm.md`**.

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
  stop seeing the alarm and fall back to `FALLBACK_ALARM_HOUR` — i.e. the wrong
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
  cache → `FALLBACK_ALARM_HOUR`. The cache bounds remote reads to ~288/day
  despite the per-minute tick.
- **A record older than `PUBLISHED_ALARM_MAX_AGE_SECONDS` (14 days) is skipped
  at every step, including the cache.** The check is on when the *phone
  stamped it*, never on when we fetched — checking the fetch is trivially
  defeated, because the cache is rewritten from the same stale record every few
  minutes, so `fetched_at` is always fresh however old the record behind it is.
  That is why the winning HLC's instant is carried through `_alarm_payload` →
  `_sync_transport` → the cache's `published_at`. Expiring is safe because
  `FALLBACK_ALARM_HOUR` *is* the phone's baseline. An **undated** record is
  trusted, not expired: the GitHub mirror has no per-field HLC, so treating
  "cannot tell" as "too old" would break that backend entirely.
- **Degraded reads log at INFO, not WARNING.** `get_alarm()` runs every minute,
  so a persistent condition logged loudly is 1440 identical journal lines a day.
  `_trigger` emits the single WARNING that matters: it is firing *now* on a
  non-phone alarm time.

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
reach the running service. Convention: `~/wake-alarm`, mirroring
`~/screen-locker`.

If you add a dependency and only install it into a dev venv, the service fails
with `ModuleNotFoundError` on its next run — this exact gap caused a 3-day
diet_guard outage. Verify against `/usr/bin/python3 -c "import <dep>"`.

## Uninstalling

`uninstall.sh`, never `rm -rf` on the repo. `/usr/local/bin/shutdown` is
root-owned and shadows `/usr/bin/shutdown`; deleting the repo leaves it in
place, and with the alarm cache gone it falls through to
`sudo rtcwake … ; exec systemctl hibernate` — so `shutdown now` would silently
stop being a poweroff, every day, forever.

`install.sh` calls `uninstall.sh --retired-only` as its last step, so
**`uninstall.sh` is load-bearing for installing**, not just for removing —
renaming or deleting it breaks a fresh install. That call is non-fatal and
gated on `sudo -n`: the cleanup needs root, and a hard failure there would
abort an install that had already placed the package and enabled the timer.

**`/etc/sudoers.d/wake-alarm` is deliberately left in place** even by a full
uninstall: screen-locker's own `_wake_alarm.py:_schedule_rtcwake` still shells
out to `sudo rtcwake`, and removing the entry here breaks a live feature in
another repo with no error message anywhere.

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
- Lint: `pre-commit run --all-files`
- Show the resolved alarm: `python -m wake_alarm._sync --show` (`--no-cache` forces a live read)
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
  to `requests`, and don't make the `crdt_sync` import unconditional.
- Don't forget the orchestrator when changing this package's module paths.
- Don't point the trigger at anything but `morning-routine.service`, or the
  workout lock never runs.
- Don't remove the trigger's once-per-day latch.
- Don't raise the log level of `_sync`'s degraded-read paths.
- Don't let the bypass skip the walk, and don't add a challenge kind that
  hides its own prompt.
- Don't make `HomeScreen.initState` concurrent again, and don't collapse
  `publish()`'s two failure messages back into one.
- Don't date a record by when the PC fetched it.
- Don't delete `/etc/sudoers.d/wake-alarm`.
- Don't commit `wake_state.json`.
