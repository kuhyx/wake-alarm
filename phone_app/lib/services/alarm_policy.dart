import 'package:shared_preferences/shared_preferences.dart';

/// The alarm schedule, which the user cannot weaken.
///
/// The alarm is deliberately **not** opt-in: there is no "set alarm" button to
/// forget and no cancel to reach for at 02:00. The time is baked in, and the
/// only edit the UI offers is moving the *next* alarm **earlier**.
///
/// Earlier-only is what makes this tamper-resistant: every change the user can
/// make costs them sleep, so a half-asleep user has no lever that helps them
/// stay in bed. Moving it later, disabling it, or skipping a day are simply
/// not expressible.
class AlarmPolicy {
  /// Creates a policy for a given override, if one is active.
  const AlarmPolicy({this.overrideHour, this.overrideMinute});

  /// The baseline wake hour. Everything else ratchets down from here.
  static const int baselineHour = 8;

  /// The baseline wake minute.
  static const int baselineMinute = 0;

  /// SharedPreferences key for a one-shot earlier override (minutes of day).
  static const String kOverrideKey = 'alarmPolicy.overrideMinutes';

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

  /// Minutes-of-day for the baseline, used to reject non-earlier edits.
  static const int _baselineMinutes = baselineHour * 60 + baselineMinute;

  /// Loads the policy, applying any active one-shot override.
  static Future<AlarmPolicy> load() async {
    final prefs = await SharedPreferences.getInstance();
    final stored = prefs.getInt(kOverrideKey);
    if (stored == null || stored >= _baselineMinutes) {
      // A stored value at or after the baseline would be a weakening, so it is
      // ignored rather than trusted — the store is not a trust boundary.
      return const AlarmPolicy();
    }
    return AlarmPolicy(
      overrideHour: stored ~/ 60,
      overrideMinute: stored % 60,
    );
  }

  /// Records a one-shot earlier alarm, returning false if it is not earlier.
  ///
  /// Rejecting a later time is the whole point: this is the only write the UI
  /// exposes, so it must be incapable of buying the user extra sleep.
  static Future<bool> setEarlier(int hour, int minute) async {
    final minutes = hour * 60 + minute;
    if (minutes >= _baselineMinutes) return false;
    final prefs = await SharedPreferences.getInstance();
    final existing = prefs.getInt(kOverrideKey);
    // Ratchet: an active override can only be moved earlier still, never
    // relaxed back towards the baseline.
    if (existing != null && minutes >= existing) return false;
    await prefs.setInt(kOverrideKey, minutes);
    return true;
  }

  /// Clears the one-shot override, returning to the baseline.
  ///
  /// Called after the alarm fires. Without this the first early start would
  /// become permanent, and the user would have no way back to 08:00 short of
  /// reinstalling — a one-way ratchet with no reset is a trap, not a defence.
  static Future<void> resetAfterFire() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(kOverrideKey);
  }
}
