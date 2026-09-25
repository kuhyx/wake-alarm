import 'dart:math' as math;

// The baseline wake time, lowered one minute per calendar day to 07:00.
//
// "Cooking the frog": 2026-09-25 is the last 08:00 morning, 2026-09-26 rings
// at 07:59, and so on until 2026-11-24 reaches the 07:00 floor, which is then
// permanent. The time is a pure function of the date the alarm *fires* on —
// no counter, no stored start date — so neither a reinstall nor wiped app
// data can reset the ramp. Every calendar day counts, free days included, so
// free days cannot stall it.
//
// Mirrored by `AlarmRamp.kt` (native re-arm) and `wake_alarm/_ramp.py` (PC
// fallback and clamp); `wake_alarm/tests/test_ramp.py` parses both copies
// and fails when the constants drift.

/// The last day at the old 08:00 baseline; each day after it is a minute
/// earlier.
final DateTime rampAnchor = DateTime.utc(2026, 9, 25);

/// Minutes of day on the anchor date (08:00).
const int rampStartMinutes = 8 * 60;

/// The floor the ramp stops at, for good (07:00).
const int rampFloorMinutes = 7 * 60;

/// Baseline wake time on [day]'s local calendar date, in minutes of day.
///
/// Only the date of [day] matters. Days are counted between UTC midnights
/// built from the local y/m/d, so a DST change (2026-10-25 is inside the
/// ramp) cannot turn a 23- or 25-hour day into a skipped or doubled minute.
/// Days before the anchor stay at 08:00 rather than extrapolating later.
int rampMinutesOn(DateTime day) {
  final date = DateTime.utc(day.year, day.month, day.day);
  final elapsed = math.max(0, date.difference(rampAnchor).inDays);
  return math.max(rampFloorMinutes, rampStartMinutes - elapsed);
}
