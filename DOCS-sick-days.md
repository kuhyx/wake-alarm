# Sick days — the phone picker, the silent ring, the pre-alarm sync

The pool itself is `~/src/utils/sickdays` (Python): every day is normal until
it is marked sick, today or later only, no cap, no reason, never also a free
day. Read its README for the rules and the RTDB wire format. This file covers
the phone half.

On a sick day the phone does not ring, the stick does not judge the day, and
nothing ring-related is recorded. It is **not** a free day: separate pool,
separate RTDB node (`sickdays-sync/devices`), separate native cache, separate
screen, and every log line and event says `sick_day`.

## Where things are

| | |
|---|---|
| Picker | `phone_app/lib/screens/sick_days_screen.dart` (+ `sick_days_body.dart`, the shared `day_calendar.dart`); the sick-face icon on the home screen |
| Rules, Dart port | `phone_app/lib/services/sick_day_pool.dart`: records `{state: sick/cleared, actor}`, one HLC per write, never a tombstone |
| Sync | `phone_app/lib/services/sick_day_sync.dart` (shared tick: `day_pool_sync.dart`), Firebase only |
| Ring path | `android/.../SickDays.kt` (+ `DayCache.kt`), read in `AlarmReceiver` through `RingDecision.kt` |
| Stick | `StickCheck.kt`: verdict `sick_day`; the streak skips sick days like free days |
| Pre-alarm sync | `PoolSyncAlarm.kt`, `PoolSyncSchedule.kt`, `PoolSyncEngine.kt` → `poolSyncMain` → `day_pool_refresh.dart` |

## The picker

Same Monday-first grid as the free days, in `cat-2` blue (`DayMarkColors`
in `ui/theme.dart`) rather than the accent gold, under its own title and
icon. One tap marks a day sick, another clears it. **Today is tappable**
(unlike the free-day grid); the past is inert. No count, no confirmation.

## A date is never in both pools

Each picker syncs the *other* pool on open and refuses a date it holds, naming
the pool: `2026-10-20 is a free day — release it in Free days first.` /
`2026-10-20 is a sick day — clear it in Sick days first.` If the other pool
cannot be opened, every mark is refused ("could not check" never counts as
"not in it"), as `sickdays`' `ConflictCheckUnavailableError` does.
`free_day_pool.dart` itself is untouched: the check lives in the callers,
exactly as the Python README prescribes.

## The ring

`AlarmReceiver` asks `RingDecision.skip(free, sick)`. On a sick day it logs
`sick day: not ringing; re-armed for tomorrow`, appends `alarm_fired` with
`reason: "sick_day"`, re-arms and returns: no `AlarmService`, no
`RingWatch.markFired`, no headless `ring_started`. The stick's checks at
A + 15, boot and watchdog return `sick_day` for that date, so there is no
miss, no streak change and no lockdown; the stakes card says
`Sick day — no alarm, nothing at stake.`

**Fail closed.** An unreadable or missing cache is "not a sick day"
(`DayCache`), so the phone rings, matching `sickdays.is_sick_day()`.

## PC → phone before the ring, with the app closed

`sickdays add` on the PC writes locally; its sync timer pushes to RTDB. The
phone pulls from RTDB. A **pre-alarm sync** does that pull with no screen
open, so a PC mark reaches the native cache before the ring:

- `PoolSyncAlarm` arms an allow-while-idle exact alarm (request code 1006;
  inexact fallback if exact alarms are refused, never `setAlarmClock`, so it
  is never shown as the next alarm) at the earliest of **21:00** and
  **A − 30 min**. It is armed from `AlarmScheduler.schedule()`, the funnel
  every arm path uses (boot included), and re-arms itself.
- `PoolSyncReceiver` holds the broadcast open with `goAsync()` (it keeps the
  process out of the cached/frozen state) while `PoolSyncEngine` runs a
  headless Flutter engine on `poolSyncMain`. That pulls **both** pools and
  rewrites both native caches through `AlarmChannel`. Dart says `done`; a
  25 s timeout stops it regardless (the broadcast limit is 60 s).
- The ring decision stays a cache read. A network call inside
  `AlarmReceiver` would spend the alarm-clock exemption that lets
  `AlarmService` start, and a missed ring cannot be failed closed.

The guarantee is precisely this: **a day marked on the PC, and pushed by its
sync timer before 21:00 (or before A − 30), is honoured if the phone has
network at that slot.** The evening slot is the dependable one. The morning
slot usually runs in Doze, where an allow-while-idle alarm gets only a short
network window. If both fail, the cache keeps its last sync and the phone
rings. Launching the app or opening either picker also syncs both pools. The free-day pool rides along, which closes the "PC mark overnight can
miss the ring" gap `DOCS-free-days.md` used to admit.

Known edge: a sick mark that lands *after* the morning was dismissed does not
stop that session's re-rings (`REASON_RERING` is not gated); no pre-alarm
sync runs between A and the session's end anyway.

## Checks

- Dart: `test/services/sick_day_pool_test.dart` (rules + a log written by the
  real Python package), `sick_day_sync_test.dart`, `day_pool_refresh_test.dart`
  (an RTDB log from the PC reaches `setSickDays` through `runHeadlessPoolSync`),
  `test/sick_days_screen_test.dart`, `test/free_days_sick_conflict_test.dart`,
  `test/services/today_stakes_sick_test.dart`.
- Kotlin (JVM, `android/app/src/test`): `DayCacheTest`, `RingDecisionTest`,
  `PoolSyncScheduleTest`, `StickCheckSickTest`. Run with
  `cd phone_app/android && ./gradlew :app:testDebugUnitTest`, after one
  `flutter build apk` has written `gradlew` and `local.properties`.
- Cross-language: `phone_app/scripts/sick_days_interop/check.sh` writes a
  pool through Dart and reads it with `sickdays` (Python), failing on any
  disagreement. Needs `SICKDAYS_PYTHON` or the sickdays venv.

## Do NOT

- Don't fold sick days into `FreeDays`/`isFree`, or log them as `free_day`.
- Don't sync inside `AlarmReceiver`. Don't tombstone a date to clear it.
- Don't add a count, a reason prompt or a warning. There is no budget.
