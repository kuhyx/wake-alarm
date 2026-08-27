# CLAUDE.md — wake_alarm

## What this does

A wake alarm: on alarm days (`ALARM_DAYS` in `_constants.py` — currently
**every day**, `frozenset({0..6})`), the machine hibernates overnight and
wakes itself via `rtcwake` at the configured alarm time. `wake-alarm.service`
then opens a fullscreen Tk window that must be dismissed (with a typed challenge — see
`_challenges.py`), plays audio through every real sink, and optionally
toggles a TP-Link Tapo P110 smart plug via `python-kasa`.

## Scheduling — a per-minute timer, with hibernate as the fallback

The PC is **always on**. The alarm time comes from the phone, which can change
it at any hour, so nothing about the schedule may be baked in ahead of time.

**Primary path — `wake-alarm-trigger.timer`:**

1. The timer ticks every minute (`OnCalendar=*:*:00`, `Persistent=true`) and
   runs `python -m wake_alarm._trigger` — a short, stateless check-and-fire.
2. `_trigger` resolves the alarm via `_sync.get_alarm()`, builds today's fire
   instant in **local** time, and fires iff `now` is in
   `[fire_time, fire_time + TRIGGER_CATCHUP_MINUTES)`. The catch-up window is
   what makes a suspended or just-booted machine still fire.
3. Firing = `systemctl --user start morning-routine.service`. **Never**
   `wake-alarm.service` directly — see the orchestrator section below.
   Starting an already-active unit is a no-op, so an alarm on screen needs no
   extra dedupe state; the `was_alarm_dismissed_today()` /
   `was_workout_logged_today()` gates cover the rest.

A timer, not a resident daemon: each tick is a fresh process, so there is no
long-lived scheduler to die silently and no wall-clock jump to handle across
suspend/resume.

**Fallback path — hibernate (only when the PC really is powered down):**

`shutdown-wrapper.sh` (installed to `/usr/local/bin/shutdown`, shadowing
`/usr/bin/shutdown` via PATH order) still intercepts shutdown/poweroff, reads
the same synced alarm, and sets `rtcwake`. `sleep-hook.sh` (in
`/usr/lib/systemd/system-sleep/`) fires on resume (`$1 == post`) and starts
`morning-routine.service`. This is now a backstop, not the main mechanism.

If you change `WAKE_AFTER_HOURS` in `_constants.py`, you must also update the
duplicate constant in `shutdown-wrapper.sh` (`WAKE_AFTER_HOURS=8`) — they are
not wired together, by design (the shell wrapper has no Python runtime
available at the point it intercepts `shutdown`).

**The wrapper no longer talks to the network or handles a token.** It reads
`~/.config/wake_alarm/alarm_cache.json` — the cache `_sync.py` already
refreshes every minute — and falls back to `WAKE_AFTER_HOURS` if that file is
absent, malformed, or more than 2 days old. This removed the duplicated token
search order (`read_sync_token()` used to mirror `SYNC_CONFIG_FILE` /
`SYNC_TOKEN_FALLBACK_FILES`), and it is what makes the wrapper survive the
move to Firebase unchanged: an ID token expires in about an hour, and a shell
script at shutdown time has no safe way to refresh one. The only coupling left
is the cache's `{"hour","minute","fetched_at"}` shape — keep the reader in the
wrapper in step with `_write_cache()` in `_sync.py`.

## `wake-alarm.service` must never auto-start

`wake-alarm.service` deliberately has **no `[Install]` section** and nothing
starts it automatically. `_should_run_alarm()` gates on day / dismissed /
workout-logged but has **no time gate**, so a
`WantedBy=graphical-session.target` there fires the alarm at *login* time on
any alarm day — which is every day now that the machine no longer reboots into
the alarm. `install.sh` explicitly runs `systemctl --user disable
wake-alarm.service` to clear the stale symlink from older installs.

The unit survives only as a manual test handle. Do not "fix" its missing
auto-start.

## Reading the phone's alarm

`_sync.py` is the only reader of the remote alarm. `shutdown-wrapper.sh` reads
`_sync.py`'s local cache instead of the remote file, so there is no second
remote reader to keep in step.

- Source of truth: a `crdt_sync` log written by `phone_app/` under
  `wake-alarm-sync/devices/<device-id>/alarm.json`. The value lives at
  `.alarm.fields.alarm_hour[0]` / `.alarm_minute[0]`. **The same logical path
  on both backends** — Firebase's namespace mirrors the repo layout — so only
  the transport differs, never the parse.
- **The Firebase reader discovers device directories; it is not pinned to
  `devices/phone/`.** The phone's device id is migrating from the fixed
  constant `phone` to a per-install uuid, and a reader pinned to the old path
  would silently stop seeing the alarm the moment the phone migrated — then
  fall back to `FALLBACK_ALARM_HOUR`, i.e. wake at the wrong time. So
  `_fetch_firebase_alarm()` lists `SYNC_DEVICES_PREFIX`, reads every device's
  `alarm.json`, and picks the newest by the hour field's **HLC** (not by
  listing order), with `device_id` breaking exact ties so two devices stamped
  in the same millisecond don't alternate between ticks. A device whose
  payload doesn't parse is skipped rather than allowed to win.
  `SYNC_ALARM_PATH` remains as a last-resort read for a backend that lists
  nothing — keep it until every install has migrated. The **GitHub** fallback
  still reads the single fixed path; it is the mirror, not the primary.
- Payload parsing/ranking lives in `_alarm_payload.py`, split out of `_sync.py`
  so the wire format is testable without network or disk (and to keep both
  files under the 500-line cap). `_sync.py` owns fetching, caching and
  fallback; `_alarm_payload.py` owns "what did the phone actually say".
- **Firebase first, GitHub as the cutover mirror** (`fetch_remote_alarm()` is
  just `_fetch_firebase_alarm() or _fetch_github_alarm()`). Retiring the
  mirror is deleting the GitHub branch plus `SYNC_API_BASE`/`SYNC_REPO_*`.
- Firebase config: the shared `~/.config/crdt-sync/firebase.json`; the
  refresh token is cached per app under `SYNC_APP_NAME` (`wake_alarm`), so
  this app's credential is separate from its siblings'. The config file is
  checked **before** anything is constructed, so an unconfigured machine
  never touches the network.
- GitHub token (fallback path only): `~/.config/wake_alarm/sync.json` key
  `token`, else a sibling app's raw
  `~/.config/{diet_guard,screen_locker}/sync_token`. Needs `repo` scope — the
  repo is private, and a token without access returns **404, not 403**.
- `crdt_sync` is imported at module scope but **guarded by
  `try/except ImportError`**, exactly like `python-kasa` in `_smart_plug.py`:
  the service runs `/usr/bin/python`, not a venv, so a dependency that failed
  to install must degrade the read to the GitHub path rather than crash the
  per-minute trigger. The GitHub path stays stdlib-only for that reason.
  Verify with `/usr/bin/python3 -c "import crdt_sync"`, not the dev venv.
- Resolution chain in `get_alarm()`: fresh cache (< 5 min) → live fetch →
  stale cache → `FALLBACK_ALARM_HOUR`. The cache
  (`~/.config/wake_alarm/alarm_cache.json`) is what bounds remote reads to
  ~288/day despite the per-minute tick, and what keeps a network blip from
  costing a wake-up.
- **Degraded reads log at INFO, not WARNING.** `get_alarm()` runs every minute,
  so a persistent condition logged loudly is 1440 identical journal lines a
  day. `_trigger` emits the single WARNING that matters: it is firing *now* on
  a non-phone alarm time.

Check what the PC currently resolves: `python -m wake_alarm._sync --show`.
Check what it would do right now: `python -m wake_alarm._trigger --dry-run`.

## The phone rings on its own — hand-written Kotlin, one MethodChannel

`phone_app/` is no longer just a time picker. It arms and rings its own alarm
(items 1/4) through five Kotlin files behind **one** MethodChannel
(`AlarmChannel.kt`) on `MainActivity`/`AlarmActivity`:

`AlarmScheduler` (arm/cancel/re-arm) · `AlarmReceiver` (fires) ·
`AlarmService` (foreground service: wakelock, sound, vibration, full-screen
intent) · `AlarmActivity` (dismiss screen over the lockscreen) ·
`BootReceiver` (re-arm after reboot) · `StepCounter` (item 3 fallback).

**Never replace any of this with a pub plugin.** The stack is AGP 9.0.1 /
Gradle 9.1 / Kotlin 2.3.20; a plugin that will not compile against AGP 9 breaks
the build outright rather than degrading, and this is the one path that must
not break. Third-party plugins are acceptable only for droppable extras (QR
scanning) — never for the ring path.

Things that are a hard crash or a silent no-ring, not a warning:

- **`STREAM_ALARM` is load-bearing.** `AlarmService` sets
  `AudioAttributes.USAGE_ALARM`, which is what ignores DND and silent mode.
  Never `USAGE_MEDIA`/`STREAM_MUSIC` — it would be muted exactly when the
  alarm matters most.
- **`android:foregroundServiceType="mediaPlayback"` must be on the `<service>`
  in the manifest AND passed to `startForeground()`.** Omitting either is a
  hard crash the moment the alarm fires on API 34+ — and it is invisible on an
  API 33 device, which is why the API 36 AVD exists.
- **`setAlarmClock()`, not `setExactAndAllowWhileIdle()`.** It is Doze-exempt,
  needs no `SCHEDULE_EXACT_ALARM` prompt (`USE_EXACT_ALARM` covers an
  alarm-clock app), and it is what grants the receiver its foreground-service
  exemption when it fires with the screen off.
- **`FLAG_IMMUTABLE` on every `PendingIntent`** — mandatory since API 31; a
  mutable one throws at arm time.
- **`canUseFullScreenIntent()` gates, it does not warn.** From API 34 the grant
  can be revoked; `_armOwnAlarm()` in `home_screen.dart` refuses to report
  success and tells the user to grant it, because without it the alarm posts a
  notification the sleeping user never sees.
- **`min/target/compileSdk` are pinned explicitly** (28/36/36) in
  `android/app/build.gradle.kts`. They used to be delegated to the Flutter
  Gradle plugin, so there was no floor to reason about. minSdk 28 is what makes
  `android:showWhenLocked`/`turnScreenOn` plain manifest attributes.

**Re-arm has three hooks, and needs all three.** `LogStore` has **no change
stream** (the plan claimed one; it does not exist in `crdt_sync_dart`), so the
picker's save is only one of them: `main()`'s startup `rearm()`,
`BOOT_COMPLETED`, and the dismiss handler. Drop any one and the alarm rings
once and then silently stops.

**The phone rings daily**, matching the PC's `ALARM_DAYS` (all seven days).
The two are deliberately not synced — a shared day set is item 8's shape, and
diverging defaults would have the halves firing on different days.

`lib/services/challenge.dart` is a port of `_challenges.py`'s five kinds so
both halves behave identically; `kDismissCodeLength`/`kDismissFlashSeconds`
are **duplicated** from `_constants.py`, not synced. Change one, change both.

Room proof (item 3) is `lib/services/room_proof.dart`: **NFC or QR satisfies
on its own; steps alone never does** — the phone is stationary while you walk
to it, so steps only accrue after pickup and can be faked by shaking it in
bed. Steps are accepted only together with elapsed time, as the fallback for
when both other mechanisms fail.

Emulator: `wake_alarm_api36` (Pixel 6a profile, API 36). The SDK tools are at
`~/Android/Sdk` but **not on PATH** — export `ANDROID_HOME` and add
`cmdline-tools/latest/bin`, `emulator` and `platform-tools` yourself.

## Module map

`_alarm.py` owns the window and the dismiss flow and nothing else. The full
map of which module answers which question, the HDMI-silence root cause, and
the timing constants that must not collide are in **`DOCS-architecture.md`**.
Read it before changing the escalation or the failsafe.

## Cross-repo coupling — not a bug

`_constants.py`'s `WORKOUT_LOG_FILE` points at
`~/screen-locker/screen_locker/workout_log.json` — a file owned by the
separate, already-standalone `screen-locker` repo
(https://github.com/kuhyx/screen-locker). This is intentional: the alarm
reads whether today's workout was already logged by screen-locker to decide
whether the morning routine should also lock the workout screen. If this
path ever raises `ModuleNotFoundError`-style confusion, the bug is almost
certainly in the **orchestrator** (`morning_routine` in testsAndMisc), not
here — see the next section.

## The morning_routine orchestrator lives elsewhere

`morning_routine._orchestrator` (in `testsAndMisc/python_pkg/morning_routine/`)
runs this package and `screen_locker` as two sequential subprocesses. When
either package is extracted to its own repo, **the orchestrator's module
reference must be updated in the same change** — this exact mistake
(orchestrator left pointing at `python_pkg.screen_locker.screen_lock` after
screen-locker's extraction on 2026-05-28) caused a month-long silent
production failure where the alarm fired and dismissed correctly but the
workout lock crashed with `ModuleNotFoundError` on every run. Once both
`wake_alarm` and `screen_locker` are pip-installed system-wide, the
orchestrator needs no `PYTHONPATH`/`cwd` plumbing — plain
`subprocess.run([sys.executable, "-m", module, "--production"])` resolves
both.

## Production dependency installation — read this before adding any dependency

`wake-alarm.service` runs `/usr/bin/python` directly — **not** a venv. Any
new non-stdlib dependency (this package itself, `gatelock`, `python-kasa`,
anything added later) must be installed into system Python's *user*
site-packages:

```bash
/usr/bin/python3 -m pip install --user --break-system-packages -e .
```

**Always run `install.sh` (or `pip install -e`) from a durable clone, not a
scratch directory.** `install.sh` does `pip install -e "$REPO_DIR"` —
editable, so a later `git pull` in that same clone updates the running
production code with no reinstall needed. The clone must live somewhere
permanent (this repo's convention: `~/wake-alarm`, mirroring `~/screen-locker`
for the screen-locker package) — if you `pip install -e` from `/tmp/...` or
run `pip install "wake_alarm @ git+https://..."` as a one-off, you get a
non-editable snapshot frozen at that commit, and the next `git push` here
silently does **not** reach the running service.

`install.sh` already does this. **If you add a dependency and only install it
into a dev venv, the production service will silently fail with
`ModuleNotFoundError` on its next run** — this exact gap caused a 3-day
diet_guard production outage (2026-06-19 to 2026-06-22) for the sibling
`gatelock` migration. Always verify against
`/usr/bin/python3 -c "import <new_dep>"`, not just the dev venv, before
considering a dependency change done.

## Operational gotchas

- **`python-kasa` is optional at runtime** (`_smart_plug.py` catches
  `ImportError` and disables smart-plug control with a warning log), but it
  *is* a hard dependency for this repo's own tooling (mypy/pylint/tests need
  it importable) — see `pyproject.toml`/`requirements.txt`.
- **The `wave` module needs special pylint handling.** `_audio.py` opens WAV
  files in write mode; pylint's stdlib stub infers the read-mode overload and
  wrongly flags `setnchannels`/`setsampwidth`/`setframerate`/`writeframes` as
  missing. See the `generated-members` list in `pyproject.toml`'s
  `[tool.pylint.typecheck]` — don't remove it if pylint starts complaining
  about `wave.Wave_write`.
- **`wake_state.json` is runtime state, not tracked.** It holds the
  HMAC-signed dismissal record for the current alarm day. It used to be
  accidentally committed in the monorepo; it is gitignored here and must
  stay that way.

## Commands

- Run tests: `python -m pytest wake_alarm/tests/ --cov=wake_alarm --cov-branch --cov-fail-under=100`
- Lint: `pre-commit run --all-files`
- Test the lock manually (safe, closeable): `python -m wake_alarm._alarm --demo`
- Show the resolved alarm: `python -m wake_alarm._sync --show` (add
  `--no-cache` to force a live GitHub read)
- Show what the next tick would do: `python -m wake_alarm._trigger --dry-run`
- Watch it live: `journalctl --user -fu wake-alarm-trigger.service`
- Install for production: `bash install.sh`
- Gate the shell/system scripts: `bash scripts/vmbox/harness.sh`
  (disposable Arch VM; what it covers and what it cannot is in
  **`DOCS-vmbox.md`** — notably *not* audio, the phone, or the
  bootloader). A sandbox pass never proves the host is fine.

Note the dev venv lacks `gatelock`, so anything importing `_state` (including
`_trigger`) must be run with `/usr/bin/python3`, not `.venv/bin/python`.

## Do NOT

- Don't add a dependency without doing the production install-path check
  above. `_sync.py`'s **GitHub** path is stdlib-only for exactly this reason —
  don't "improve" it to `requests`, and don't make the `crdt_sync` import
  unconditional: the `try/except ImportError` guard is what keeps a failed
  install from killing the trigger.
- Don't forget the orchestrator when changing this package's module path or
  invocation — see "The morning_routine orchestrator lives elsewhere" above.
- Don't give `wake-alarm.service` an `[Install]` section or enable it. It
  fires at login time, not alarm time — see the section above.
- Don't make the trigger start `wake-alarm.service`; it must start
  `morning-routine.service` so the workout lock still runs.
- Don't raise the log level of the routine degraded-read paths in `_sync` —
  the per-minute tick turns any WARNING there into journal spam.
- Don't commit `wake_state.json`.
