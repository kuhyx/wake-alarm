/// The wake-enforcement numbers the app shows, in one place.
///
/// The single Dart source for every number on the stakes card and the ring
/// line (`DOCS-wake-enforcement.md`). Each one mirrors a Python constant in
/// `wake_alarm/_constants.py`, and `wake_alarm/tests/test_stakes_mirrors.py`
/// parses this file and fails when they drift -- keep each value a plain
/// literal on its own line.
library;

/// A time of day, as the Python side's `(hour, minute)` tuples.
typedef ClockTime = ({int hour, int minute});

/// No dismiss this long after the alarm is a miss (`SESSION_NONE_GRACE`).
const stickGrace = Duration(minutes: 15);

/// A started morning is exempt this long (`SESSION_PROVISIONAL_GRACE`).
const provisionalGrace = Duration(minutes: 90);

/// ...and never past this time of day (`SESSION_PROVISIONAL_CAP`).
const ClockTime provisionalCap = (hour: 9, minute: 30);

/// A morning finished in time keeps the PC open until this time of day
/// (`SESSION_COMPLETED_UNTIL`).
const ClockTime completedUntil = (hour: 11, minute: 0);

/// The PC rings when no ring started this long after the alarm
/// (`FALLBACK_PHONE_SILENT_AFTER`).
const pcPhoneSilentAfter = Duration(minutes: 2);

/// The PC's fallback ring stops after this long (`FALLBACK_RING_CAP`).
const pcRingCap = Duration(minutes: 30);

/// A lockdown spans at most this many calendar days, today included
/// (`STICK_LOCKDOWN_MAX_DAYS`).
const stickLockdownMaxDays = 5;

/// The escape hatch's last usable day, inclusive (`ESCAPE_HATCH_LAST_DAY`).
final escapeHatchLastDay = DateTime(2026, 10, 15);

/// An escape needs a typed reason at least this long
/// (`ESCAPE_REASON_MIN_CHARS`).
const escapeReasonMinChars = 40;

/// Whether the escape hatch is still open on [now]'s calendar day.
///
/// Date-only and inclusive: [escapeHatchLastDay] is midnight, so comparing
/// instants would close the hatch at 00:00:01 on its last day.
bool escapeHatchOpen(DateTime now) =>
    !DateTime(now.year, now.month, now.day).isAfter(escapeHatchLastDay);
