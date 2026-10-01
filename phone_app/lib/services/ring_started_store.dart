import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';
import 'package:wake_alarm_sync/services/iso_time.dart';

/// Today's `ring_started` record: `{"date", "at"}`, set when the ring screen
/// first opens.
///
/// This is the ping the PC's fallback alarm waits for: no `ring_started` by
/// A + 2 min means the phone is silent, and the PC rings. Kept locally so a
/// publish that failed during the ring is retried by every later sync.
abstract final class RingStartedStore {
  /// SharedPreferences key holding the JSON record.
  static const key = 'enforcement.ringStarted';

  /// SharedPreferences key holding the date whose record reached the PC.
  static const publishedKey = 'enforcement.ringStartedPublished';

  /// The stored record, or null when none or malformed.
  ///
  /// Reloaded first: the headless engine the alarm starts and the ring
  /// screen's engine each cache preferences, and a stale cache would let
  /// the second overwrite the first ring of the day.
  static Future<Map<String, Object?>?> load() async {
    final prefs = await _fresh();
    final text = prefs.getString(key);
    if (text == null) return null;
    try {
      final decoded = jsonDecode(text);
      return decoded is Map ? Map<String, Object?>.from(decoded) : null;
    } on FormatException {
      return null;
    }
  }

  /// Records [now] as today's ring start, unless today already has one.
  ///
  /// The first of the day wins: a re-ring or a probe reopens the ring
  /// screen, and moving the stamp later would hide when the phone actually
  /// started ringing.
  static Future<Map<String, Object?>> recordFirst(DateTime now) async {
    final existing = await load();
    if (existing != null && existing['date'] == isoDate(now)) return existing;
    final entry = <String, Object?>{
      'date': isoDate(now),
      'at': isoWithOffset(now),
    };
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(key, jsonEncode(entry));
    return entry;
  }

  /// Whether [date]'s record has already reached the backend.
  static Future<bool> publishedOn(Object? date) async =>
      (await _fresh()).getString(publishedKey) == date;

  /// Records that [date]'s record reached the backend.
  static Future<void> markPublished(String date) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(publishedKey, date);
  }

  static Future<SharedPreferences> _fresh() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.reload();
    return prefs;
  }
}
