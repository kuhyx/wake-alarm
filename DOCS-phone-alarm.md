# The phone half — how it rings, and what breaks it

Split out of `AGENTS.md` to keep that file under the repo's 250-line
gate. Read this before changing anything under `phone_app/android/` or
the ring/dismiss path in `phone_app/lib/`.

## Hand-written Kotlin, one MethodChannel

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

**`ringNow` + `lib/main_ring_probe.dart` are a deliberate manual test
handle**, the phone-side equivalent of `wake-alarm.service` on the PC: the
normal arm path needs a sync backend connected, so there is no other way to
fire the ring on an emulator. The probe runs the **real** app widget and
pushes `/ring` — an earlier version rendered its own UI and so proved nothing
about the route. `flutter build apk` uses `lib/main.dart`, so the probe is
never the shipped entrypoint; `ringNow` is reachable only over this app's own
channel and arms nothing. Do not "clean these up" without replacing the
capability.

Emulator: `wake_alarm_api36` (Pixel 6a profile, API 36). The SDK tools are at
`~/Android/Sdk` but **not on PATH** — export `ANDROID_HOME` and add
`cmdline-tools/latest/bin`, `emulator` and `platform-tools` yourself. The
phone (Pixel 6a, `23181JEGR08034`) holds a **release-signed** build, so
`phone_deploy.sh` needs `--release` or the install fails with
`INSTALL_FAILED_UPDATE_INCOMPATIBLE`.

**The ring screen must close itself on dismiss.** `AlarmActivity` handles
`closeRingScreen` (the shared `AlarmChannel` holds `applicationContext` and
cannot finish an activity). Without it the dismiss screen stays up over the
lockscreen forever — back is disabled by design in both halves — and the live
instance would carry a satisfied room proof and the solved answer into the
next ring.

