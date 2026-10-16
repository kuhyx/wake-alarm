import 'package:wake_alarm_sync/services/alarm_ramp.dart';
import 'package:wake_alarm_sync/services/enforcement_state.dart';
import 'package:wake_alarm_sync/services/stakes.dart';

/// An alarm time of day.
typedef AlarmTime = ClockTime;

/// What the stakes card says, already in words.
class StakesView {
  /// Creates a view.
  const StakesView({
    required this.title,
    required this.stakes,
    required this.pending,
    required this.streak,
  });

  /// "Today · Thu 2 Oct — stick day".
  final String title;

  /// What the coming morning costs or earns.
  final List<String> stakes;

  /// A lockdown, penalty or escape already in force.
  final List<String> pending;

  /// The streak line.
  final String streak;
}

/// The stakes of the next undecided morning, from the native [state].
///
/// That is today while today's alarm is still open (not dismissed, not
/// excused, not past A + [stickGrace]), tomorrow after -- in the evening,
/// today's stakes are history. Today uses the stored alarm `A`, the one the
/// native check judges by; tomorrow uses [nextAlarm] (the policy's next
/// time), falling back to `A`. Every number comes from `stakes.dart`.
StakesView describeStakes({
  required DateTime now,
  required EnforcementState state,
  AlarmTime? nextAlarm,
}) {
  final today = state.today;
  final stored = _stored(state);
  final todayOpen =
      stored != null &&
      !state.dismissedToday &&
      !state.escapedToday &&
      now.isBefore(_at(today, stored).add(stickGrace));
  final day = todayOpen ? today : _plusDays(today, 1);
  final alarm = todayOpen ? stored : (nextAlarm ?? stored);
  final free = todayOpen ? state.freeToday : state.freeTomorrow;
  final sick = todayOpen ? state.sickToday : state.sickTomorrow;
  final when = todayOpen ? 'Today' : 'Tomorrow';
  final stick = isWorkday(day);
  final kind = free
      ? 'free day'
      : sick
      ? 'sick day'
      : (stick ? 'stick day' : 'carrot day');
  final lines = <String>[];
  if (alarm == null) {
    lines.add('No alarm armed yet — nothing at stake.');
  } else if (free) {
    lines.add('Free day — no alarm, nothing at stake.');
  } else if (sick) {
    lines.add('Sick day — no alarm, nothing at stake.');
  } else {
    final ringAt = _at(day, alarm);
    if (stick) {
      final lock =
          (todayOpen ? state.lockIfMissToday : state.lockIfMissTomorrow) ??
          _plusDays(day, 1);
      final next = todayOpen
          ? "tomorrow's"
          : "${_weekday(_plusDays(day, 1))}'s";
      lines.add(
        'Miss (no dismiss by ${hhmm(ringAt.add(stickGrace))}) → apps '
        'locked through ${formatDay(lock)} + $next PC leniency gone',
      );
    } else {
      lines.add(
        'Finish the morning by ${hhmm(carrotCutoff(ringAt))} → PC open '
        'until ${_hhmm(completedUntil.hour, completedUntil.minute)}',
      );
    }
    lines.add(
      'PC rings at ${hhmm(ringAt.add(pcPhoneSilentAfter))} if the phone is '
      'silent (up to ${pcRingCap.inMinutes} min)',
    );
  }
  return StakesView(
    title: '$when · ${formatDay(day)} — $kind',
    stakes: lines,
    pending: _pending(state),
    streak:
        'Streak: ${state.streak} missed stick '
        'day${state.streak == 1 ? '' : 's'} in a row',
  );
}

/// The ring screen's one line: the stick-day consequence of not dismissing,
/// or null when this ring has none (not a stick day, free, sick, already
/// dismissed, excused or missed).
String? ringStakesLine(EnforcementState state) {
  final stored = _stored(state);
  if (stored == null ||
      !isWorkday(state.today) ||
      state.freeToday ||
      state.sickToday) {
    return null;
  }
  if (state.dismissedToday || state.escapedToday) return null;
  if (state.lastMiss == state.today) return null;
  final by = _at(state.today, stored).add(stickGrace);
  final lock = state.lockIfMissToday ?? _plusDays(state.today, 1);
  return 'Stick day: no dismiss by ${hhmm(by)} → apps locked through '
      '${formatDay(lock)}';
}

/// The carrot's cutoff for a morning whose alarm rings at [ringAt]:
/// `min(A + provisionalGrace, provisionalCap)`, the PC's own rule.
DateTime carrotCutoff(DateTime ringAt) {
  final cap = DateTime(
    ringAt.year,
    ringAt.month,
    ringAt.day,
    provisionalCap.hour,
    provisionalCap.minute,
  );
  final relative = ringAt.add(provisionalGrace);
  return relative.isBefore(cap) ? relative : cap;
}

List<String> _pending(EnforcementState state) {
  final today = state.today;
  final locked = state.lockedThrough;
  return <String>[
    if (state.escapedToday) 'This morning is excused ("That was a bug").',
    if (locked != null && !locked.isBefore(today) && !state.escapedToday)
      'Apps locked through ${formatDay(locked)}.',
    if (state.lastMiss == today && !state.escapedToday)
      "Missed this morning → tomorrow's PC leniency is gone.",
  ];
}

AlarmTime? _stored(EnforcementState state) {
  final hour = state.alarmHour;
  final minute = state.alarmMinute;
  return hour == null || minute == null ? null : (hour: hour, minute: minute);
}

// Built from fields, never day + Duration: DST would shift the wall clock.
DateTime _at(DateTime day, AlarmTime t) =>
    DateTime(day.year, day.month, day.day, t.hour, t.minute);

DateTime _plusDays(DateTime day, int n) =>
    DateTime(day.year, day.month, day.day + n);

/// `HH:MM` of [t].
String hhmm(DateTime t) => _hhmm(t.hour, t.minute);

String _hhmm(int h, int m) =>
    '${h.toString().padLeft(2, '0')}:${m.toString().padLeft(2, '0')}';

const _weekdays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const _months = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', //
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
];

String _weekday(DateTime day) => _weekdays[day.weekday - 1];

/// "Fri 3 Oct".
String formatDay(DateTime day) =>
    '${_weekday(day)} ${day.day} ${_months[day.month - 1]}';
