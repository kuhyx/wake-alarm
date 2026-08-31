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
not break. Third-party plugins are acceptable only for droppable extras —
never for the ring path, and never for NFC or the step counter, both of which
the dismiss sequence now hard-depends on.

Things that are a hard crash or a silent no-ring, not a warning:

- **`STREAM_ALARM` is load-bearing — but it does not beat *every* DND mode.**
  `AlarmService` sets `AudioAttributes.USAGE_ALARM`; never
  `USAGE_MEDIA`/`STREAM_MUSIC`, which would be muted exactly when the alarm
  matters most. Measured on the Pixel 6a (2026-08-27), the muted-stream mask
  from `dumpsys audio` differs by zen mode:

  | DND mode | `zen_mode` | `STREAM_ALARM` |
  |---|---|---|
  | priority (`ZEN_MODE_IMPORTANT_INTERRUPTIONS`) | 1 | **not muted** (mask `0x1a6`) |
  | total silence (`ZEN_MODE_NO_INTERRUPTIONS`) | 2 | **MUTED** (mask `0x9be`) |

  The confirmed ring was under **priority DND** (`zen_mode=1`): player
  `state:started`, `usage=USAGE_ALARM` → `STREAM_ALARM(4)`, `mutedState:none`.
  **Total silence mutes the alarm stream system-wide**, and no audio flag
  escapes it — so "ignores DND" means priority DND, not total silence. If that
  gap ever matters, the fix is a zen-policy check at arm time, not an audio
  change. `raiseAlarmVolume()` does run on this hardware (observed raising
  `oldIndex:0` → 7, no `SecurityException`), which recovers a stream turned
  down to zero but not one muted by total silence.
- **The ring fades in; the stream still goes to max.** Two different knobs,
  and merging them trades a gentle start for a silent alarm.
  `raiseAlarmVolume()` fixes the *system stream* — a stream left at 0 would
  silence the alarm outright. `startVolumeRamp()` climbs the *player's own
  gain* from `RAMP_START_GAIN` (0.04) to full over `RAMP_DURATION_MS` (60 s),
  quadratically, because perceived loudness is not linear in amplitude.
  Measured on the Pixel 6a (2026-08-31) from `dumpsys media.audio_flinger`
  track gain: −28 dB at 3 s, −21 dB at 15 s, −12 dB at 30 s, 0 dB at 62 s.
  Every step re-reads `player`, and `stopSound()` drops the queue before
  releasing it, so a dismissal mid-ramp cannot touch a released `MediaPlayer`.
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

`lib/services/challenge.dart` owns the four challenge kinds. **Every kind
must keep its prompt on screen until it is answered.** A memorise-then-hide
kind existed once and was deleted outright: the ring screen is reached by
walking in from another room, so anything already gone by the time the user
looks at it is unsolvable, not merely hard.

Room proof is now a **strict, latched sequence**, owned by
`lib/services/dismiss_gate.dart`:

    tag 1  ->  25 steps + 2 min  ->  tag 2  ->  3 challenges

Every stage is required, they must happen **in that order**, and a stage once
passed **never reverts** — an unknown or out-of-order tag is ignored rather
than clearing progress. `room_proof.dart` answers only "did this one check
pass just now"; the ordering lives in the gate. Two *distinct* tags are
required: the same id in both slots is refused at registration, because one
tag satisfying both stages removes the walk that is the entire point.

Steps still require elapsed time as well as a count — the phone is stationary
while you walk to it, so a bare count can be faked by shaking it in bed. That
pair is unchanged from when steps were a fallback; it is only its role that
changed, from alternative to prerequisite.

**The bypass is the only fallback, and it is deliberately narrow.** After
`DismissGate.bypassAfter` (5 minutes) of ringing, or immediately when NFC is
off or fewer than two distinct tags are registered, the two *tag* stages are
skipped and the challenge count rises to 6. **The walk is never skipped** —
jumping straight to the challenges would let someone lie in bed for five
minutes and answer questions without standing up, which is weaker than the
gate this replaced. Without some such hatch a dead tag at 06:00 leaves an
alarm that literally cannot be switched off.

## Home presence — the alarm knows where it is

Away from home the two tags are screwed to walls in another city, so the
sequence is unsatisfiable. `HomePresence.read` (Kotlin) reports raw
observations and `lib/services/home_presence.dart` decides; away skips the two
*tag* stages and **keeps the normal 3 challenges**. The walk still counts.

- **Never "modernise" `WifiManager.getConnectionInfo()`.** It is deprecated at
  API 31 in favour of `NetworkCapabilities.getTransportInfo()`, and that
  replacement does not work here: the *synchronous*
  `ConnectivityManager.getNetworkCapabilities()` redacts every
  location-sensitive field, so `transportInfo` is null and the BSSID silently
  vanishes. Measured on the Pixel 6a (API 36, 2026-08-31) — connected to a
  known AP, fine location granted, location services on — the capabilities
  route returned `ssid=null bssid=null` while the GPS fallback quietly covered
  for it. Un-redacted `transportInfo` needs a `registerNetworkCallback`.
- **A redacted BSSID is `02:00:00:00:00:00`, not null and not an error.**
  Android returns it when fine location is missing *or* location services are
  off. Untreated it is a valid-looking MAC that never matches, so every
  morning reads "away" and the ritual silently stops happening.
- **Unreadable means away** — the user's explicit choice. A revoked permission
  therefore weakens the alarm rather than breaking it loudly, which is why
  `HomePresenceLine` puts the verdict *and its cause* on the home screen.
  **Unconfigured is not unreadable:** an install that never captured a home
  keeps the strict sequence, or shipping this would have deleted the gate.
- **Presence resolves before the missing-tags bypass** (`ring_startup.dart`).
  Both skips latch one-way, so whichever fires first fixes the count; the
  other order would give every away morning with NFC off the punitive 6.
  Equally, `activateBypass()` is refused after `activateAwayProfile()` — the
  ring screen's 5-minute timer fires unconditionally and an away morning
  crosses 5 minutes routinely.
- **Registration passes `withFix: true`; the ring screen does not.** A Wi-Fi
  answer short-circuits GPS, which is what makes the verdict instant at home —
  but it also meant capture never recorded a coordinate, so the GPS fallback
  could only ever be configured with Wi-Fi off, i.e. never.
- **BSSIDs are a list, and the SSID matches too.** A dual-band router answers
  to a different BSSID per band and the phone roams overnight; one stored
  address would call a band switch "travelling".
- The read runs from `AlarmActivity` (foregrounded, so while-in-use location
  suffices). **Do not move it into `AlarmService`** — that would mean
  `foregroundServiceType="mediaPlayback|location"` plus
  `FOREGROUND_SERVICE_LOCATION`, on the one path that must not break.

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

**Never pass `--build-number` by hand**, including for the probes: use
`phone_deploy.sh <app> --release --target lib/main_ring_probe.dart` and let it
pick. Android compares versionCode only upward, so a hand-picked number puts
the phone above what CI will mint and locks CI out until the commit count
catches up — the only other escape is an uninstall, which wipes the NFC tags,
the home location and the sync identity. This happened on 2026-08-31 (probe
builds at 200/201 stranded the phone at 207 against a ceiling of 156).
`.versioncode-offset` at the repo root is the recovery valve, read by **both**
`release-apk.yml` and the local gate so the two can only move together; it is
currently 101. `hooks/build_number_guard_pretool.sh` now blocks the bypass.

**The ring screen must close itself on dismiss.** `AlarmActivity` handles
`closeRingScreen` (the shared `AlarmChannel` holds `applicationContext` and
cannot finish an activity). Without it the dismiss screen stays up over the
lockscreen forever — back is disabled by design in both halves — and the live
instance would carry a satisfied room proof and the solved answer into the
next ring.
