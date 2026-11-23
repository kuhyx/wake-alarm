# Bypasses of the alarm (2026-11-22)

On 2026-11-20 and 11-22 kuhy long-pressed WakeAlarm on the home screen and
tapped "Wstrzymaj aplikację" (Digital Wellbeing's *Pause app*). The pause
suspended the app, the ring stopped, and he went back to sleep. This file
covers the three layers that now stop that, what counts as a bypass when
one gets through anyway, and what a bypass costs.

## Layer 1: the pause is refused (focus-owner, `~/src/phone-focus-mode`)

Every focus-owner pass, for the eight enforcement apps in
`focus_policy/packages.py` `ENFORCEMENT_PACKAGES` (wake_alarm_sync,
workout_app, diet_guard_app, leetcode_guard, book_guard_app, home_guard,
daily_limits, habit_stack):

- `setUserControlDisabledPackages`: Android refuses to suspend them
  (`Cannot suspend package ...: protected package`), and Settings' Force stop
  and Clear storage are greyed out. `am force-stop` and `pm clear` are refused
  too; `adb install -r` still works, so deploys are unaffected.
- `setUninstallBlocked`.
- `setPermissionGrantState(POST_NOTIFICATIONS, GRANTED)`. The full-screen
  intent is an app-op and cannot be pinned (`setPermissionGrantState`
  returns false), so revoking it is a bypass instead (below).
- A suspension found anyway is lifted. Measured on the emulator: a pause
  made before the pins were applied was lifted 4.3 s later, by the pass that
  wake_alarm's `UNSUSPEND` signal started.

Digital Wellbeing itself is hidden in every state (`ALWAYS_BLOCKED_PACKAGES`),
so the Pause button is gone as well.

## Layer 2: WakeAlarm is a device admin

`WakeAdminReceiver` (`res/xml/wake_admin.xml`, no policies). Android refuses
to suspend an active admin. It is activated over adb, never by a tap:

    adb shell dpm set-active-admin com.kuhy.wake_alarm_sync/.WakeAdminReceiver

Deactivating it in Settings cannot be prevented, so it is a bypass.

## Layer 3: what counts as a bypass (`Bypass.kt`)

A bypass counts only on a ringing day (an alarm is stored, not a free or sick
day, the ring did not stand down) while the ring or the morning session is
live. Causes (`bypass` phone event, `data.cause`):

| cause | seen by |
|---|---|
| `suspended` | `SuspendReceiver` on `MY_PACKAGE_SUSPENDED`; also sends focus-owner `UNSUSPEND` |
| `admin_removed` | `WakeAdminReceiver.onDisabled` |
| `notifications_off` | ring start and every launch (`Bypass.checkOnLaunch`) |
| `fsi_revoked` | the same; uid app-op `USE_FULL_SCREEN_INTENT` denied |
| `ring_killed` | every launch and boot: today's ring fired, was never dismissed, and is not sounding |
| `uninstalled` | focus-owner, every pass, any day: `com.kuhy.wake_alarm_sync` not installed for user 0 (see below) |

`ring_killed` reads `watched_fired_date`, a stamp only builds with `Bypass`
write, so a ring fired by an older build (11-22, paused, never dismissed) does
not count the first time the new build starts. The same cause twice within
a minute is recorded once (both activities run the launch check).

## What a bypass costs

- **A miss** (`StickCheck`), on any weekday, at once, whatever the dismiss
  does afterwards: a lockdown through the next day, stacking. The streak
  links penalty days, stick days (Tue–Thu) plus bypass days; free and sick
  days are skipped. A plain late dismiss on Fri–Mon still changes nothing.
  A later check or bypass on the day already penalised sends the stored
  lockdown (`locked_through`, if today or later) again, same date and
  streak, so a signal focus-owner missed (not running, not yet Device
  Owner) still lands.
- **The phone rings again** (`Bypass.ringAgain`). During a session it is a
  re-ring: only the full dismiss sequence silences it and `re_rings` goes up
  by one when it does (`SessionHandoff.afterDismiss`). It is recorded as
  `bypass:<cause>` in `re_ring_reasons` (`bypass:fsi_revoked`,
  `bypass:suspended`, ...): `Bypass.record` stamps the cause
  (`BypassReRing`, dated) before it restarts the ring, and the session takes
  it once over `takeBypassReRing`, on the screen's tick or on the dismiss. A
  bypass while a deadline re-ring already sounds stamps nothing: one sound,
  one re-ring, reason `deadline:<leg>`; the `bypass` event, its publish and
  the lockdown still happen.
- **The PC rings** (`_fallback_policy`, reason `bypass`). The phone pushes
  the event at once through the headless `publishNowMain` engine. The PC
  rings from the bypass for up to 30 min (`FALLBACK_RING_CAP` from the
  bypass, not the day's cap), outside the window, after a session started
  and after the day's own ring was used. It stops on a `dismissed` newer
  than the bypass, which the phone also pushes at once. Free and sick days
  and an escape stand it down. The tick reads the phone until `A + 4 h`
  (`BYPASS_WATCH`); the fallback timer ticks 04:00-11:59 (and 21:xx, below).
  To see these answers without a backend, `_fallback --dry-run --at <instant>
  --published <file>` reads the phone's logs from a JSON list of
  `[device_id, alarm.json]` pairs instead of Firebase (`_published_file`).

## An uninstall that gets through (focus-owner, 2026-11-23)

WakeAlarm cannot be uninstalled: focus-owner holds `setUninstallBlocked`
and `setUserControlDisabledPackages` on it every pass. The Pixel's
`dumpsys device_policy` shows `packageUninstallBlocked` for it (2026-11-23).
On the AVD, `adb uninstall`, `pm uninstall --user 0` and `-k --user 0` all
fail with `DELETE_FAILED_INTERNAL_ERROR` ("Attempted to delete protected
package"): the user-control pin refuses it before the uninstall block is
asked. Deploys use `adb install -r`, which both allow.

If WakeAlarm is gone anyway, WakeAlarm cannot record a bypass, so
focus-owner does (`phone-focus-mode` `focus-owner/.../UninstallLockdown.kt`,
`UninstallEvents.kt`, `lib/sync/`):

- **Missing** means not found, or found with `FLAG_INSTALLED` clear. A
  hidden app is installed.
- **Lockdown**, every day including free and sick days: the lockdown
  allowlist while the app is missing and through the day after it returns.
  Its own prefs, so wake_alarm's `LIFT_LOCKDOWN` does not clear it (a
  reinstalled WakeAlarm would send one at once). No day cap.
- **Event**: `bypass` with `cause: uninstalled` and the phone-local `date`,
  under device `focus-owner`, record `alarm`, field `phone_events`. One at
  once when the app goes missing (it rings the PC only inside a tick
  window), then one per later day at the first pass at or after the alarm
  time focus-owner read from the sync (08:00 if none). The PC rings every
  morning until a full dismiss logs `dismissed`; on a free or sick day it
  stays silent while the phone stays locked.
- **Queue**: the lockdown never waits on the push. An unsent event is
  retried every pass, a failure is logged once a day, nothing is dropped.
- **Push-only**: focus-owner writes its own file and never merges a peer's
  log into it (a pulled list would replace its events, field by field).
  Its `phone_events` HLC is the newest event's own `at`, so a late retry
  never out-ranks a list the reinstalled phone published.
- `newest_push` skips device `focus-owner`: its write is not the phone's.
- Set up once per install: Google sign-in plus the passphrase (the cloud
  and lock icons in focus-owner's app bar). Each success pushes a harmless
  `install_check` field that no PC policy reads.

## Testing against a backend: the RTDB emulator

The AVD never signs in to prod. A probe build with
`--dart-define=WAKE_SYNC_EMULATOR=http://10.0.2.2:9000` syncs to the
Firebase RTDB emulator on the PC instead of prod Firebase *and* the GitHub
mirror (`sync_emulator.dart`; plain HTTP is allowed to `10.0.2.2` in the
debug manifest only). Release builds never set the define.

1. `systemd-run --user --collect --unit=wa-rtdb-emu /usr/bin/java -jar
   ~/.cache/firebase/emulators/firebase-database-emulator-v4.11.2.jar --host
   127.0.0.1 --port 9000` (one default namespace; `auth=owner` is admin).
2. Write a dummy passphrase to `files/passphrase` under the app's
   `Android/data/<pkg>/` dir; the probe moves it into the keystore on launch
   (`probe_passphrase.dart`). Without one every push is `sync locked`.
   A probe's `-t` file must re-export the headless entrypoints
   (`publishNowMain`, ...): Kotlin resolves them by name in the root library,
   and without them the bypass publish never ran.
3. After the bypass: `HOME=<scratch with .config/crdt-sync/password>
   PYTHONUSERBASE=~/.local /usr/bin/python3 scripts/emu_published.py
   http://127.0.0.1:9000 out.json`, then `_fallback --dry-run --at <instant>
   --published out.json`.

Traps on the shared AVD:

- It can boot `RUNNING_LOCKED` with PIN 1234, and then `/sdcard` is missing.
  Unlock it before you write the passphrase.
- `dpm remove-active-admin` refuses the admin ("non-test admin"). Use
  Settings → Device admin apps → WakeAlarm → Deactivate.
- An active admin makes `cmd package suspend` fail, so suspend first, then
  activate the admin.
- The probe's `ringNow` does not mark the ring as fired, so `Bypass.record`
  logs "no ring or session live". Set the AVD clock (`adb root`,
  `settings put global auto_time 0`, `date`) to just before the armed
  `AlarmReceiver` time and let the alarm fire. Afterwards set `auto_time`
  back to 1.

### Live check 2026-11-22: bypass events on the RTDB emulator

C5 and C6 were checked on emulator-5556 with the `main_session_probe.dart`
build (`WAKE_SYNC_EMULATOR`), with the clock moved to Mon 2026-11-23 07:56
so the 07:57 alarm rang through `AlarmReceiver`. With the alarm still
ringing: `cmd package suspend` at 07:57:34 logged `bypass: suspended`,
and deactivating the admin in Settings at 07:58:04 logged
`bypass: admin_removed`. Each one logged "signalling focus-owner lockdown
through 2026-11-24". `emu_published.py` then read both from the RTDB emulator:
`{"kind":"bypass","data":{"cause":"suspended","date":"2026-11-23"}}` and
`{"kind":"bypass","data":{"cause":"admin_removed","date":"2026-11-23"}}`
(a `notifications_off` bypass from 07:57:11 was also there, because the AVD
has the app's notifications off). Then
`_fallback --dry-run --at 2026-11-23T08:03 --published out.json` answered
`WOULD RING: bypass` (`bypass_at=07:58:04`). focus-owner is not on that AVD:
its unsuspend and its applied lockdown are the earlier C6 check at 83e1e15.

## The 21:00 notifications check

Android lets nothing lock "All WakeAlarm notifications", and with them off
the ring has no screen. The ring-time check above still counts it as a
bypass; this one catches it the evening before, while kuhy can still fix it.

- **Phone.** `NotifState` (the same rule `Bypass.checkPermissions` uses: app
  notifications off, or the ring channel at `IMPORTANCE_NONE`) logs a
  `notifications` event, data `enabled` (bool) and `trigger`, and pushes it
  at once through `publishNowMain`. Triggers: an exact alarm at 21:00
  (`NotifAlarm`, request code 1007, `evening`; re-armed by its receiver, by
  every `AlarmScheduler.schedule`, boot and the watchdog, always the next
  future 21:00) and `NotifBlockReceiver` on `APP_BLOCK_STATE_CHANGED` /
  `NOTIFICATION_CHANNEL_BLOCK_STATE_CHANGED` for the ring channel
  (`app_block`, `channel_block`). Both receivers hold the broadcast open
  (`NotifRules.holdMs`: 8 s for a foreground broadcast, whose ANR budget is
  10 s, else 25 s) so the headless engine is not frozen mid-push.
- **PC** (`_fallback_evening`, rule in `_evening_policy`). The fallback
  timer also ticks 21:00-21:59; those ticks skip the morning code. When
  today's newest `notifications` event says off, the PC rings
  (`notifications_off`) until a newer one says on, or 30 min
  (`FALLBACK_RING_CAP`) from the evening's first ring. The cap has its own
  latch, `evening_ring.json`, so it never eats the morning's or a bypass's.
  The hour gates only *starting*; a ring started at 21:50 runs its 30 min.
- **No ring** when tomorrow is a free or sick day (`free_tomorrow`,
  `sick_tomorrow`), when no event was published today (phone off), or when
  Firebase does not answer at the tick. An unreachable poll mid-ring keeps
  ringing. Events: `evening_tick`, `evening_ring_start`, `evening_ring_stop`
  (never the morning's names, so the audit does not count them).

## The monitors ring too

kuhy turns the speakers off at the knob for the night, so the 11-22 fallback
ring played 30 min into silence. Both rings now also play to every connected
monitor (ELD name in `aplay -l`: `G27Q` on HDMI, `VG28UQL1A` on DP, both on
the NVidia card):

- root path: `ring_alsa.sh` starts one `aplay` loop per monitor, IEC958
  unmuted;
- PipeWire path: `_ring_monitors.MonitorLoops` runs
  `ring_alsa.sh --monitors` as the user beside `pw-play` (PipeWire does not
  expose the NVidia outputs).

Each monitor logs one `ring_sink sink=<name> ... result=ok|error` line.

**Silent probe.** `ring_alsa.sh --probe` writes two seconds of digital
silence to each monitor with IEC958 muted (restored afterwards) and logs one
`ring_probe` line per monitor. `_ring_probe.maybe_probe` starts
`wake-alarm-ring-probe.service` once, at `A − 5` on the first morning with no
graphical session (the state a fallback ring meets), and writes
`ring_probe_done`. "No graphical session" means greeter only: lightdm is
masked only before 05:00, when no ring can happen. A morning kuhy is already
logged in at `A − 5` logs one `ring_probe: waiting_for_no_session` event a
day instead. Read it with `journalctl -u wake-alarm-ring-probe` and
`grep ring_probe ~/.local/state/wake_alarm/events.jsonl`.
vmbox gate: `ring-alsa-monitor-sinks`, `ring-alsa-monitor-probe`
(`scripts/vmbox/guest_cases_monitors.sh`).

## Found on the way: lockdown signals never arrived

focus-owner defined `SIGNAL_LOCKDOWN` but did not request it, and wake_alarm
sends with it as the receiver permission, so every `LOCKDOWN_UNTIL_EOD` and
`LIFT_LOCKDOWN` was dropped. focus-owner now holds it (eeb0def).
