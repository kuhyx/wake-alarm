import 'package:wake_alarm_sync/services/stakes.dart';

/// Which kind of morning the stakes describe.
enum StakesDayKind {
  /// A booked free day: nothing rings.
  free,

  /// A marked sick day: nothing rings.
  sick,

  /// A workday: a miss locks the apps.
  stick,

  /// A weekend day: finishing in time opens the PC early.
  carrot,
}

/// What the stakes card shows: the facts, and the same facts in words.
///
/// The card paints only the facts (glyphs, times, dates); the sentences are
/// its spoken labels and what the tests read for the wording. Built by
/// `describeStakes` in `today_stakes.dart`.
class StakesView {
  /// Creates a view.
  const StakesView({
    required this.title,
    required this.stakes,
    required this.pending,
    required this.streak,
    required this.kind,
    required this.isToday,
    required this.day,
    required this.streakCount,
    this.dismissBy,
    this.lockThrough,
    this.finishBy,
    this.pcOpenUntil,
    this.pcRingAt,
    this.escapedToday = false,
    this.lockedThrough,
    this.missedToday = false,
  });

  /// The kind of the coming morning.
  final StakesDayKind kind;

  /// Whether the coming morning is today (else tomorrow).
  final bool isToday;

  /// The coming morning's date.
  final DateTime day;

  /// Missed stick days in a row.
  final int streakCount;

  /// Stick day: the dismiss deadline. Null when nothing is armed.
  final DateTime? dismissBy;

  /// Stick day: the last day a miss locks the apps through.
  final DateTime? lockThrough;

  /// Carrot day: the time the morning must be finished by.
  final DateTime? finishBy;

  /// Carrot day: how long a finished morning keeps the PC open.
  final ClockTime? pcOpenUntil;

  /// When the PC rings if the phone stays silent. Null when nothing rings.
  final DateTime? pcRingAt;

  /// This morning was excused.
  final bool escapedToday;

  /// Apps already locked through this day, when a lockdown is in force.
  final DateTime? lockedThrough;

  /// This morning was missed (and not excused).
  final bool missedToday;

  /// "Today · Thu 2 Oct — stick day" (spoken).
  final String title;

  /// What the coming morning costs or earns (spoken, one per row).
  final List<String> stakes;

  /// A lockdown, penalty or escape already in force (spoken, one per row).
  final List<String> pending;

  /// The streak line (spoken).
  final String streak;
}
