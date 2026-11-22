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
  by one when it does (`SessionHandoff.afterDismiss`).
- **The PC rings** (`_fallback_policy`, reason `bypass`). The phone pushes
  the event at once through the headless `publishNowMain` engine. The PC
  rings from the bypass for up to 30 min (`FALLBACK_RING_CAP` from the
  bypass, not the day's cap), outside the window, after a session started
  and after the day's own ring was used. It stops on a `dismissed` newer
  than the bypass, which the phone also pushes at once. Free and sick days
  and an escape stand it down. The tick reads the phone until `A + 4 h`
  (`BYPASS_WATCH`); the fallback timer ticks 04:00-11:59 (and 21:xx, below).

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
`ring_probe_done`. Read it with `journalctl -u wake-alarm-ring-probe`.
vmbox gate: `ring-alsa-monitor-sinks`, `ring-alsa-monitor-probe`
(`scripts/vmbox/guest_cases_monitors.sh`).

## Found on the way: lockdown signals never arrived

focus-owner defined `SIGNAL_LOCKDOWN` but did not request it, and wake_alarm
sends with it as the receiver permission, so every `LOCKDOWN_UNTIL_EOD` and
`LIFT_LOCKDOWN` was dropped. focus-owner now holds it (eeb0def).
