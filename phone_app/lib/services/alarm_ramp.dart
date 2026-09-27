import 'dart:math' as math;

// The baseline wake time, lowered one *earned* minute at a time to 07:00.
//
// "Cooking the frog": a Monday/Friday/Saturday/Sunday morning whose alarm
// rang and was dismissed that same day earns one minute, and the alarm moves
// a minute earlier from the next non-workday on. Workdays (Tue/Wed/Thu) earn
// nothing and hold the latest earned time; a free day never rings so it earns
// nothing; a missed alarm earns nothing. 07:00 is the floor, for good.
//
// The earned dates are a grow-only set (`RampProgress`, synced so a reinstall
// gets them back): each date counts once, so no bug can run it away, and the
// time is a pure function of the set and the day the alarm fires on.

/// Mirror of `freedays.WORKDAYS` (Tue/Wed/Thu), which Dart cannot import;
/// `wake_alarm/tests/test_workday_mirrors.py` fails when it drifts.
const Set<int> workdays = {
  DateTime.tuesday,
  DateTime.wednesday,
  DateTime.thursday,
};

/// Minutes of day before anything was earned (08:00).
const int rampStartMinutes = 8 * 60;

/// The floor the ramp stops at, for good (07:00).
const int rampFloorMinutes = 7 * 60;

/// Minutes earned before earned dates were recorded: the three dismissed
/// mornings that had already taken the alarm to 07:59 (Sat), 07:58 (Sun) and
/// 07:57 (Mon) when the ramp stopped being a pure calendar count, 2026-09-27.
const Set<String> rampSeedDates = {'2026-09-25', '2026-09-26', '2026-09-27'};

/// Whether [day] is a weekly workday, on which the ramp holds.
bool isWorkday(DateTime day) => workdays.contains(day.weekday);

/// `YYYY-MM-DD` of [day]'s local calendar date.
String rampDateKey(DateTime day) =>
    '${day.year.toString().padLeft(4, '0')}-'
    '${day.month.toString().padLeft(2, '0')}-'
    '${day.day.toString().padLeft(2, '0')}';

/// Baseline wake time for an alarm firing on [day], in minutes of day.
///
/// Counts the earned non-workday dates strictly before the most recent
/// non-workday on or before [day], so a minute earned on Monday first shows on
/// Friday and Tuesday-Thursday ring at Monday's time. Date keys compare as
/// strings, so DST cannot skew the count.
int rampMinutesOn(DateTime day, Set<String> earned) {
  var step = DateTime(day.year, day.month, day.day);
  while (isWorkday(step)) {
    step = DateTime(step.year, step.month, step.day - 1);
  }
  final cutoff = rampDateKey(step);
  final counted = {...earned, ...rampSeedDates}.where((key) {
    final date = DateTime.tryParse(key);
    return date != null && key.compareTo(cutoff) < 0 && !isWorkday(date);
  });
  return math.max(rampFloorMinutes, rampStartMinutes - counted.length);
}
