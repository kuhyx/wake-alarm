# Free days — the phone picker for the shared pool

The pool itself is `~/src/utils/freedays` (Python): one global set of days on
which every gate app stands down, 35 per calendar year, declared for today or
later, never backdated, refunded only while still in the future. Read its
README for the rules. This file covers the phone half, which lives in this
repo because the alarm is the one gate where standing down is a physical
event — the phone stays silent — rather than an absent dialog.

## Where things are

| | |
|---|---|
| Picker | `phone_app/lib/screens/free_days_screen.dart` (+ `free_days_body.dart`, `free_day_calendar.dart`), the calendar icon on the home screen |
| Rules, Dart port | `phone_app/lib/services/free_day_pool.dart` — same record shape as the Python package, byte for byte |
| Sync | `phone_app/lib/services/free_day_sync.dart` — Firebase only, `freedays-sync/devices/<uuid>/free_days.json` |
| Ring path | `android/.../FreeDays.kt` + the check at the top of `AlarmReceiver.onReceive` |

## The calendar

A Monday-first month grid (adapted from punchme's, whose own free days are a
separate concept and are not read here). One tap per future date: an empty day
is booked with no reason prompt, a booked day is released and refunded. Today
and the past are read-only — releasing a day that has started still spends
it. Tue/Wed/Thu (`workdays`, mirroring `freedays.WORKDAYS`) are shaded; past
free days stay visible, faded. Months run from January of this year to
December of next. The "Booked ahead" list below keeps reasons from PC marks
and its own Release buttons.

## Why there is a native cache

The alarm fires from Kotlin with no Flutter engine running, so at 08:00 the
Dart pool is unreadable. Dart hands the current free dates to
`FreeDays.store` (channel method `setFreeDays`) after **every** mark, release
and sync; `AlarmReceiver` reads that set before starting `AlarmService`. On a
free day it logs `free day: not ringing; re-armed for tomorrow` and returns —
nothing rings, nothing is shown, and the next morning is normal.

**Fail closed.** An unreadable or missing cache is "not a free day", matching
`freedays.is_free_day()` on the PC: a corrupt pool restores the normal rules,
it never silences the alarm. Verified on the `wake_alarm_api36` AVD
(2026-09-11, `adb root` + `am broadcast --include-stopped-packages -n
…/.AlarmReceiver`): today in the set → skip line, no service; a different
date → service start; a garbage XML file → service start.

## What reaches the phone when

- **Marked on the phone:** immediate. The cache is rewritten before the sync
  even runs, so an offline phone still stands down on a day it marked itself.
- **Marked on the PC (`freedays mark …`):** on the phone's next sync, which
  happens at app launch and whenever the picker opens. The ring path takes
  no background dependency by design (see `DOCS-phone-alarm.md`), so **a day
  marked on the PC overnight can miss the morning ring.** Mark on the phone,
  or open the app once after marking on the PC.

## Cross-language check

The Dart port is a second implementation of the rules, so it is verified
against the Python one rather than against itself:
`scripts/free_days_interop/check.sh` (a pre-commit hook on both inputs)
writes one pool through `FreeDayPool` — mark, mark today, mark+release a
future day, mark+release after arrival — replays the same edits through
`freedays.mark`/`release` into a scratch pool, and fails unless the free set,
spent set, `remaining` and `is_free_day` verdicts agree. Dart's own numbers
are never the reference: comparing them to what Python reads from Dart's
file cannot see a drift in what Dart *writes*. Proved on 2026-09-11 by
dropping the sticky `consumed` from `release` — the gate reported
`remaining: dart=33 python=32`. Needs the freedays venv
(`~/src/utils/freedays/install.sh`).

## Do NOT

- Don't give this namespace a GitHub mirror. The alarm record keeps its
  mirror because un-migrated installs depend on it; this pool never had one.
- Don't tombstone a date to un-mark it. crdt tombstones are monotonic; a
  deleted date could never be marked again. Flip `state` to `cleared`.
- Don't write `consumed` back to `false`. It is the sticky flag that stops
  two devices either side of midnight from refunding a day already used.
- Don't add a warning, a notification or a ring-time prompt. The pool is
  consulted silently; the count is shown only when the picker is opened.
