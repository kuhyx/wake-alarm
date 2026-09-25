import 'package:shared_preferences/shared_preferences.dart';
import 'package:wake_alarm_sync/services/alarm_ramp.dart';

/// The alarm schedule, which the user cannot weaken.
///
/// The alarm is deliberately **not** opt-in: there is no "set alarm" button to
/// forget and no cancel to reach for at 02:00. The time is baked in — the
/// daily ramp in `alarm_ramp.dart`, 08:00 down to 07:00 a minute a day — and
/// the only edit the UI offers is moving the *next* alarm **earlier**.
///
/// Earlier-only is what makes this tamper-resistant: every change the user can
/// make costs them sleep, so a half-asleep user has no lever that helps them
/// stay in bed. Moving it later, disabling it, or skipping a day are simply
/// not expressible.
class AlarmPolicy {
  /// Creates a policy for the next alarm's baseline and optional override.
  const AlarmPolicy({
    required this.baselineHour,
    required this.baselineMinute,
    this.overrideHour,
    this.overrideMinute,
  });

  /// Resolves the next alarm after [now], given a [stored] one-shot override.
  ///
  /// The ramp is evaluated for the day the alarm will actually **fire** on,
  /// not the day it is armed: `main()` and the home screen usually arm the
  /// evening before, and evaluating "today" there would arm tomorrow at
  /// today's (one minute later) time, every single day. Today is tried
  /// first; tomorrow always qualifies because the ramp never moves later.
  factory AlarmPolicy.resolve(DateTime now, int? stored) {
    final today = DateTime(now.year, now.month, now.day);
    var policy = AlarmPolicy._forDay(today, stored);
    // Built from fields, not today + Duration: on a DST day local midnight
    // plus N minutes is not N minutes past midnight on the wall clock.
    final at = DateTime(
      now.year,
      now.month,
      now.day,
      policy.hour,
      policy.minute,
    );
    if (!at.isAfter(now)) {
      policy = AlarmPolicy._forDay(
        DateTime(now.year, now.month, now.day + 1),
        stored,
      );
    }
    return policy;
  }

  factory AlarmPolicy._forDay(DateTime day, int? stored) {
    final base = rampMinutesOn(day);
    // A stored value at or after the baseline would be a weakening, so it is
    // ignored rather than trusted — the store is not a trust boundary.
    final override = stored != null && stored < base ? stored : null;
    return AlarmPolicy(
      baselineHour: base ~/ 60,
      baselineMinute: base % 60,
      overrideHour: override == null ? null : override ~/ 60,
      overrideMinute: override == null ? null : override % 60,
    );
  }

  /// SharedPreferences key for a one-shot earlier override (minutes of day).
  static const String kOverrideKey = 'alarmPolicy.overrideMinutes';

  /// Hour of the ramp baseline on the day the next alarm fires.
  final int baselineHour;

  /// Minute of the ramp baseline on the day the next alarm fires.
  final int baselineMinute;

  /// Hour of the active override, or null when running at the baseline.
  final int? overrideHour;

  /// Minute of the active override, or null when running at the baseline.
  final int? overrideMinute;

  /// The hour the next alarm should fire at.
  int get hour => overrideHour ?? baselineHour;

  /// The minute the next alarm should fire at.
  int get minute => overrideMinute ?? baselineMinute;

  /// Whether an earlier-than-baseline override is currently in force.
  bool get isOverridden => overrideHour != null;

  /// Loads the policy for the next alarm after [now] (default: the clock).
  static Future<AlarmPolicy> load({DateTime? now}) async {
    final prefs = await SharedPreferences.getInstance();
    return AlarmPolicy.resolve(
      now ?? DateTime.now(),
      prefs.getInt(kOverrideKey),
    );
  }

  /// Records a one-shot earlier alarm, returning false if it is not earlier.
  ///
  /// Rejecting a later time is the whole point: this is the only write the UI
  /// exposes, so it must be incapable of buying the user extra sleep. The bar
  /// is the next alarm as it stands — the ramp baseline, or an active
  /// override, which can only be moved earlier still.
  static Future<bool> setEarlier(int hour, int minute, {DateTime? now}) async {
    final minutes = hour * 60 + minute;
    final current = await load(now: now);
    if (minutes >= current.hour * 60 + current.minute) return false;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setInt(kOverrideKey, minutes);
    return true;
  }

  /// Clears the one-shot override, returning to the baseline.
  ///
  /// Called after the alarm fires. Without this the first early start would
  /// become permanent, and the user would have no way back to the ramp short
  /// of reinstalling — a one-way ratchet with no reset is a trap, not a
  /// defence.
  static Future<void> resetAfterFire() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(kOverrideKey);
  }
}
