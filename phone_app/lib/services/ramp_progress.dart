import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';
import 'package:wake_alarm_sync/services/alarm_ramp.dart';

/// The dates whose dismissed alarm earned the ramp a minute.
///
/// A grow-only set: a date is added once and never removed, so recording is
/// idempotent and the ramp can move at most one minute per earning day --
/// the property a bare counter lacks (a re-run or a duplicate sync would
/// double-count it). Synced as a union (`settings_sync.dart`), so a reinstall
/// or a second install gets every earned minute back.
class RampProgress {
  const RampProgress._();

  /// SharedPreferences key holding the earned dates as a JSON list.
  static const String kEarnedKey = 'ramp.earnedDates';

  /// The earned date keys (`YYYY-MM-DD`); unreadable storage reads as none.
  static Future<Set<String>> load() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(kEarnedKey);
    if (raw == null) return <String>{};
    try {
      final decoded = jsonDecode(raw);
      if (decoded is List) return decoded.whereType<String>().toSet();
    } on FormatException {
      // A corrupt value earns nothing rather than crashing the arm path.
    }
    return <String>{};
  }

  /// Records that the alarm firing on [now]'s date was dismissed.
  ///
  /// Only a non-workday earns: on Tuesday-Thursday the ramp holds. Returns
  /// whether a new date was added.
  static Future<bool> recordDismiss(DateTime now) async {
    if (isWorkday(now)) return false;
    return await merge(<String>{rampDateKey(now)});
  }

  /// Unions [dates] into the stored set; returns whether it grew.
  static Future<bool> merge(Iterable<String> dates) async {
    final current = await load();
    final merged = {...current, ...dates.where(_isDateKey)};
    if (merged.length == current.length) return false;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(kEarnedKey, jsonEncode(merged.toList()..sort()));
    return true;
  }

  /// Only canonical `YYYY-MM-DD` keys: the ramp compares them as strings.
  static bool _isDateKey(String key) {
    final date = DateTime.tryParse(key);
    return date != null && rampDateKey(date) == key;
  }
}
