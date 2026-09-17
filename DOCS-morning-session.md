# The morning session — what happens after the ring stops

The ring proved you stood up. It did not stop you lying back down: the
2026-09-16 observation was "I do the tags, the walk and the questions, and
then go back to sleep". So since that day **the dismiss does not end the
morning**. It hands over, inside the same `AlarmActivity`, to a silent
checklist that only ends when you are showered, dressed and sitting at the
desk — and the alarm comes back if a step is missed or the phone lies still.

Owner: `phone_app/lib/services/morning_session.dart` (the record),
`session_rules.dart` (what moves it), `screens/session_screen.dart` (the
driver), `session_handoff.dart` (how the ring reaches it).

## The legs

```
weigh in  ->  bathroom tag (≤ 2 min later)  ->  shower  ->  bathroom tag again
          ->  wardrobe tag  ->  desk tag  ->  done
```

| leg | passes when | window (re-ring at) | notes |
|---|---|---|---|
| `bathroomIn` | bathroom tag with a *pending* weight ≤ 2 min old | start + 10 min | the typed weight is not a leg; the tag is what proves you walked to the scale |
| `showerDone` | bathroom tag **≥ 8 min** after `bathroomIn` | `bathroomIn` + 18 min | its own window: 10 min composed with the 8-min floor would be a two-minute target, hit wet |
| `dressed` | wardrobe tag | previous + 10 min | |
| `atDesk` | desk tag | previous + 10 min | |

Legs latch like the ring's stages. A leg whose tag is not registered is
**skipped at start** (`LegPass.skipped`), so the feature is usable before it
is configured: with no session tags at all it is a weigh-in and nothing
else. Away from home (`RingSkip.away`) there is no session.

**Weight.** Typed, 30–250 kg; more than 3 kg from the last confirmed value
must be typed twice (`weight_entry.dart`). Without a bathroom tag the typed
value passes the first leg by itself — there is nothing to walk to.

## What rings, and how

- **A missed window** re-rings through an **AlarmManager alarm**
  (`AlarmScheduler.scheduleReRing`, request code 1003, `setAlarmClock` like
  the daily one). Not a Dart timer: the session screen can be killed, paused
  or rebooted away, and the deadline has to survive all three. `BootReceiver`
  restores it; `restoreReRing` drops an instant that has already passed
  (see *Gotchas*).
- **No still-phone check.** An accelerometer watch (`MotionMonitor.kt`, 4 min
  without motion) existed for one day and was deleted on 2026-09-17: it only
  ran while the session screen was in front, and the real routine leaves the
  app on purpose (a podcast before the shower), so it was off for most of the
  session and never rang on the one morning it was watched. The deadlines are
  the only re-ring. Do not bring it back as a foreground service without a
  morning that shows a lie-in the ≤ 10-minute windows missed.
- When Dart rings a deadline itself it routes to `/ring` afterwards, in case
  the full-screen intent lands on the live `singleInstance` activity instead
  of recreating it.
- **Silencing a re-ring is the full dismiss sequence**: tag 1, the walk,
  tag 2, three questions. The ring screen's `_finishDismiss` sees a live
  session for today and resumes it with `reRings + 1`.
- **One re-ring per leg.** After a deadline re-ring is dismissed the leg is
  in `deadlineRung`; 5 min after its deadline (`bypassGrace`) it passes as
  `LegPass.bypassed` — the dead-tag hatch, paid for with one full ring.
- **Three re-rings per morning** (`maxReRings`). A window missed with none
  left ends the session as `failed`, silently. This is the agreed cap and the
  known weakness: three rings of misery buy silence.
- The Dart tick also rings a deadline the native alarm should have fired
  (20 s grace) — ringing twice is harmless, missing it is not.

Everything is **persisted after every change** (`session_store.dart`,
`session.current`) and driven by wall-clock instants, because a re-ring
replaces the whole Flutter engine and resumes from the store.

## Leaving the app, and coming back

The checklist lives in `AlarmActivity` (NFC reader mode and the kept-on
screen are asserted there), and the launcher starts `MainActivity`. Until
2026-09-17 a home gesture or a recents swipe therefore lost the screen for
good: the re-ring still fired, but the app opened on the home screen with no
way back to the leg. Now **every launch while the morning is live lands in
`AlarmActivity`**, and the home screen is unreachable until the session is
over:

- `MainActivity.resumeMorning()` runs in `onCreate` *and* `onResume` (the
  activity is `singleTop`; a warm instance never re-runs `onCreate`), before
  any Dart and before the permission prompt — a permission dialog must never
  come up over a ring. It starts `AlarmActivity` with the `route` extra and
  finishes itself.
- It decides natively, from `SessionNotice.kt`: a cache Dart rewrites on
  every leg change (`updateSessionNotice`, always paired with `armReRing` in
  `session_notice.dart`) holding the session's **date** and the leg label.
  A cache dated any other day is ignored, never resumed — the phone dying
  mid-morning must not open a dead checklist the next evening. Flutter's
  own preferences file is deliberately not parsed from Kotlin.
- **A sounding ring wins.** `AlarmService.running` routes the launch — and
  `AlarmActivity.getInitialRoute()` — to `/ring` whatever the extra says,
  so a swiped-away ring reopened from the launcher gets the dismiss
  sequence, not the home screen or a checklist over the noise.
- **An ongoing notification** ("Morning session — Tap the bathroom tag",
  counting down to the re-ring) is one tap back to the leg. Silent channel,
  `setOnlyAlertOnce`, native chronometer, so Dart posts it per leg, not per
  tick. `finishSession` is the only thing that cancels it. The launcher
  redirect is the guarantee; the notification is the convenience.
- `main_session_probe.dart` asks `morningLive` before its test ring, so a
  relaunch of the probe during a session resumes rather than rings.

## History and sync

Finished sessions go to `session.history` (30 kept). The home screen shows
the last seven (`home_history_card.dart`) with weight deltas. The record
rides on the synced `alarm.json` like the ring tags do
(`session_sync.dart`): `session_tag_ids`, `morning_sessions` (14) and
`latest_weight_kg` (`{date, kg}`). The PC reads it with
`python -m wake_alarm._weight` (`wake_alarm/_weight.py`, Firebase only, same
device discovery as the alarm); diet-guard's `sync` imports that lazily to
refresh the weight behind its protein target. The PC alarm parser ignores
every field it does not name. Sessions merge per date, newest `updatedAt` wins, so a
reinstall gets its history back.

## Gotchas — each one cost a real run

- **Route replacement runs the new screen's `initState` before the old
  screen's `dispose`.** The ring screen's dispose used to clear the NFC
  handler the session had just registered, so the session never heard a tag
  (Pixel, 2026-09-16). `AlarmScheduler.clearNfcListener` now clears only if
  *that instance* registered the handler. The emulator harness gives each
  screen its own instance for the same reason.
- **Android replays `BOOT_COMPLETED` to a force-stopped app on its next
  launch.** After `am force-stop` during a test, a plain launch delivered
  BOOT_COMPLETED (`WakeAlarmBoot` log), `restoreReRing` re-armed a
  nine-minute-old deadline, and the phone rang in the evening with no session
  running. A stored instant in the past is now dropped, never fired.
- **`ValueKey<int>(syncEpoch)` twice in one `Column`** — the history card and
  the presence line — mis-reconciled silently in release and painted the old
  presence element in the card's slot. Keys in one child list must differ.
- **The steps stage's 2-minute floor** now applies only under bypass (no tag
  proved the walk). On the normal path tag 1 has already banked the steps,
  so the floor was two minutes of ringing nothing could shorten.
- **`developer.log` is invisible in release logcat.** Session and challenge
  logs use `debugPrint` (`WakeAlarmSession:`, `WakeAlarmRing:`), which is
  what the emulator harness and a bad morning are debugged from.
- The volume ramp is ten minutes to full, not one.

## Testing it without a bathroom

`lib/main_session_probe.dart` runs the real app on `FileDrivenScheduler`
(`lib/probe/`), which replaces NFC and the step count with files under
`/sdcard/Android/data/com.kuhy.wake_alarm_sync/files/`.
`phone_app/scripts/emu_morning.py` drives it:

```sh
flutter run -d emulator-5554 --debug -t lib/main_session_probe.dart > run.log
scripts/emu_morning.py --log run.log dismiss    # ring1, 30 steps, ring2, answers
scripts/emu_morning.py weight 72.4
scripts/emu_morning.py tag bath                 # then wait 8 min, tag bath again
scripts/emu_morning.py home; scripts/emu_morning.py launch   # back on the leg
scripts/emu_morning.py rering                   # the deadline broadcast, now
scripts/emu_morning.py --log run.log dismiss    # resumes at the same leg, 1/3
scripts/emu_morning.py tag ward; scripts/emu_morning.py tag desk
```

Verified this way on 2026-09-16 (API 36 AVD): the whole morning including a
re-ring and the resume; on 2026-09-17 the home-and-relaunch round trip on a
leg and during a ring. `flutter build apk --debug --target`
produced an APK that ran `main.dart` instead; `flutter run -t` did not.
The phone remains the only test of the AlarmManager deadline with the
screen off and the app swiped away.
