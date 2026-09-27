# The wake-time ramp ("cooking the frog")

The alarm starts at 08:00 and moves one **earned** minute earlier at a time,
down to a permanent 07:00. Owned entirely by the phone
(`phone_app/lib/services/alarm_ramp.dart`, `ramp_progress.dart`).

## The rule

- A **Monday, Friday, Saturday or Sunday** whose alarm rang and was dismissed
  that same day earns one minute (`RampProgress.recordDismiss`, called from the
  ring screen's dismiss before it re-arms).
- **Tuesday–Thursday** (`freedays.WORKDAYS`) earn nothing and ring at the time
  of the most recent non-workday: a minute earned on Monday first shows on
  Friday.
- A **free day** never rings, so it earns nothing. A **missed** alarm (rang,
  never dismissed) earns nothing.
- Ring time for day D = 08:00 − |earned dates before the latest non-workday
  ≤ D|, floored at 07:00.

## Why a set of dates, not a counter

The earned dates are a grow-only set: each date counts once, so a re-run, a
duplicate sync or a double dismiss cannot move the alarm twice, and nothing can
run it away. It rides the synced `alarm.json` record (`settings_sync.dart`,
field `ramp_earned_dates`) as a union, so a reinstall gets every minute back.
`rampSeedDates` holds the three mornings earned before dates were recorded
(2026-09-25/26/27).

## Where it is *not*

The PC no longer computes a ramp: it trusts the time the phone publishes,
clamped to ≤ 08:00, and falls back to 08:00. The Kotlin side has no ramp
either: the alarm only moves when a Dart dismiss earns a minute and re-arms, so
the native re-arm after a free day, a missed ring, a boot or the watchdog is
already the right time by re-using the stored one.

`workdays` in `alarm_ramp.dart` and `STICK_DAYS` in `WorkdayStick.kt` are
literal copies of `freedays.WORKDAYS`;
`wake_alarm/tests/test_workday_mirrors.py` fails when either drifts.
