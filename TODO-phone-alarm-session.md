# Next session: make the phone a real alarm (items 4, 3, 1)

REMOVE ME AFTER FINISH

Paste the block at the bottom into a fresh session. Everything above it is
context for *you*, the human, deciding whether the framing is right.

## Why this is its own session

The PC half is done (phases 0–7, `4286fcb`..`c131923`). What is left is
almost entirely new Kotlin + Dart on a bleeding-edge Android toolchain, needs
an emulator that is not installed yet, and ends in physical-device
verification. The plan calls it "biggest chunk by far. Own session."

## State of the phone app, measured 2026-08-27 (not guessed)

- `phone_app/lib/` has 3 screens and 7 services. **Zero alarm capability** —
  it is a time picker that syncs a value.
- `MainActivity.kt` exists at
  `android/app/src/main/kotlin/com/kuhy/wake_alarm_sync/MainActivity.kt` and
  is bare. `applicationId = "com.kuhy.wake_alarm_sync"`.
- **`minSdk`/`targetSdk`/`compileSdk` are all delegated** to the Flutter
  Gradle plugin (`flutter.minSdkVersion` etc.) — there is no floor, and
  full-screen-intent and foreground-service semantics cannot be reasoned
  about without one. Pin them first.
- **Only `/usr/bin/adb` is on PATH.** No `emulator`, no `avdmanager`, no
  `sdkmanager`. The emulator work in the plan needs these installed first,
  and the emulator image must be **API 36** to match the phone — the API 34
  image validates against semantics the target device does not have.

## The prompt

```
Implement items 4, 3 and 1 from TODO-hardening-continue.md in ~/wake-alarm —
the phone half of the wake alarm.

Read first, in this order:
  1. TODO-hardening-continue.md          (state, decisions, traps)
  2. ~/.claude/plans/wake-alarm-still-does-witty-toucan.md, phases 4 and 5
     (the full design, with every measured finding)
  3. CLAUDE.md                           (repo invariants)

Scope, in order:

1. Prerequisites, before any feature work:
   - Pin explicit minSdk/targetSdk/compileSdk in
     phone_app/android/app/build.gradle.kts. They are all delegated to the
     Flutter plugin today, so there is no floor to reason about.
   - Install emulator/avdmanager/sdkmanager (only adb is on PATH) and create
     an API 36 AVD. API 34 validates against semantics the phone lacks.

2. Item 4 + 1 — the phone actually rings. Hand-written Kotlin behind ONE
   MethodChannel on the existing bare MainActivity.kt, never a plugin: the
   stack is AGP 9.0.1 / Gradle 9.1 / Kotlin 2.3.20, and a plugin that will
   not compile breaks the build outright rather than degrading. Five files:
   AlarmScheduler, AlarmService, AlarmActivity, BootReceiver, AlarmChannel.
   AlarmManager.setAlarmClock(), a foreground service with a wakelock,
   STREAM_ALARM (load-bearing — it is what ignores DND and silent mode, never
   STREAM_MUSIC), a full-screen intent over the lockscreen, re-arm on
   BOOT_COMPLETED *and* on dismiss.
   Dart side: main.dart has no init seam today — it needs
   WidgetsFlutterBinding.ensureInitialized(), a navigatorKey and a route.
   Port the five challenge kinds from _challenges.py so both halves behave
   identically.

3. Item 3 — separate-room proofs. NFC or QR qualifies; steps alone does NOT
   (the phone is stationary while you walk to it, so steps only accrue after
   pickup and can be faked by shaking it in bed). Steps + elapsed time is the
   fallback when both others fail. This is a decision already taken — do not
   re-litigate it.

Constraints:
- 100% branch coverage, no new # noqa / type: ignore.
- The 250-line gate fires on STAGED files. Do not edit an oversized file this
  change does not already have to touch — that cascade cost a full revert
  last session. A new constant goes in its single consumer.
- Verify on the PHONE (23181JEGR08034) via the phone-deploy skill, not just
  the emulator. A companion-app change is not done on desktop.
- Do not touch the PC half's invariants: no [Install] on wake-alarm.service,
  _state.py stays UTC-keyed (screen_locker mirrors that helper), the trigger
  starts morning-routine.service.

Item 8 (mutual gating) depends on this and is the session after. Item 13
(black screen) is a different repo, host-only, and blocks nothing.
```

## After that session

- **Item 8, mutual gating.** Phone challenge first, then PC, with a bounded
  escape: if sync is unreachable ~600 s the PC gate degrades to
  locally-solvable and logs a WARNING. Without it, a Firebase outage means you
  can neither dismiss nor get to work. This is the phase that legitimately
  touches `_sync.py`, so it carries that file's 371-line split.
- **Item 13, black screen.** `~/testsAndMisc/linux_configuration` plus /boot
  and /etc. Host-only — vmbox is BIOS/GRUB and this machine is UEFI, so a
  guest pass there is actively misleading.
