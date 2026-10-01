import 'package:wake_alarm_sync/services/iso_time.dart';

/// The native stick, as the stakes card and the ring line read it.
///
/// Parsed from `EnforcementChannel.kt`'s `enforcementState` map. Every value
/// is decided natively (`StickCheck.kt`); Dart only displays it, so the date
/// on screen is the date a miss would actually lock through.
class EnforcementState {
  /// Creates a state; every field mirrors one key of the native map.
  const EnforcementState({
    required this.today,
    required this.dismissedToday,
    required this.escapedToday,
    required this.freeToday,
    required this.freeTomorrow,
    required this.streak,
    this.alarmHour,
    this.alarmMinute,
    this.lockedThrough,
    this.lastMiss,
    this.updatedAt,
    this.lockIfMissToday,
    this.lockIfMissTomorrow,
  });

  /// Parses the native map; null when it is absent or malformed.
  static EnforcementState? fromMap(Map<Object?, Object?>? map) {
    if (map == null) return null;
    final today = _date(map['today']);
    if (today == null) return null;
    return EnforcementState(
      today: today,
      alarmHour: map['alarmHour'] as int?,
      alarmMinute: map['alarmMinute'] as int?,
      dismissedToday: map['dismissedToday'] == true,
      escapedToday: map['escapedToday'] == true,
      freeToday: map['freeToday'] == true,
      freeTomorrow: map['freeTomorrow'] == true,
      streak: (map['streak'] as int?) ?? 0,
      lockedThrough: _date(map['lockedThrough']),
      lastMiss: _date(map['lastMiss']),
      updatedAt: map['updatedAt'] as String?,
      lockIfMissToday: _date(map['lockIfMissToday']),
      lockIfMissTomorrow: _date(map['lockIfMissTomorrow']),
    );
  }

  /// The phone's local date when this was read.
  final DateTime today;

  /// The stored daily alarm `A`, or null when none is armed.
  final int? alarmHour;

  /// See [alarmHour].
  final int? alarmMinute;

  /// Whether today's ring was dismissed.
  final bool dismissedToday;

  /// Whether today was excused through the escape hatch.
  final bool escapedToday;

  /// Whether today is a free day in the native cache.
  final bool freeToday;

  /// Whether tomorrow is a free day in the native cache.
  final bool freeTomorrow;

  /// Consecutive stick-day misses.
  final int streak;

  /// The current lockdown's last day, or null when none was sent.
  final DateTime? lockedThrough;

  /// The last stick day that was missed.
  final DateTime? lastMiss;

  /// ISO instant of the last change to the stick, or null before any.
  final String? updatedAt;

  /// What a miss today would lock through.
  final DateTime? lockIfMissToday;

  /// What a miss tomorrow would lock through, given the state as it is.
  final DateTime? lockIfMissTomorrow;

  /// The `stick_state` field's value (`DOCS-wake-enforcement.md`).
  Map<String, Object?> toStickStateJson() => <String, Object?>{
    'streak': streak,
    'locked_through': _iso(lockedThrough),
    'last_miss': _iso(lastMiss),
  };

  static DateTime? _date(Object? value) {
    if (value is! String) return null;
    final parsed = DateTime.tryParse(value);
    return parsed == null
        ? null
        : DateTime(parsed.year, parsed.month, parsed.day);
  }

  static String? _iso(DateTime? day) => day == null ? null : isoDate(day);
}
