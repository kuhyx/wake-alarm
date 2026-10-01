import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';
import 'package:uuid/uuid.dart';
import 'package:wake_alarm_sync/services/iso_time.dart';

/// Every use of the "That was a bug" escape hatch, newest first.
///
/// Published as the `escapes` field (`DOCS-wake-enforcement.md`): the PC
/// stops its fallback ring and drops today's penalty when it sees one, and
/// the incident report lists every use at the top. Kept locally so a failed
/// publish is retried by the next sync instead of being lost.
abstract final class EscapeLog {
  /// SharedPreferences key holding the JSON list.
  static const key = 'enforcement.escapes';

  /// How many entries the record carries.
  static const carried = 30;

  /// The stored entries, newest first; malformed storage reads as none.
  static Future<List<Map<String, Object?>>> load() async {
    final prefs = await SharedPreferences.getInstance();
    final text = prefs.getString(key);
    if (text == null) return <Map<String, Object?>>[];
    try {
      final decoded = jsonDecode(text);
      if (decoded is! List) return <Map<String, Object?>>[];
      return <Map<String, Object?>>[
        for (final entry in decoded)
          if (entry is Map) Map<String, Object?>.from(entry),
      ];
    } on FormatException {
      return <Map<String, Object?>>[];
    }
  }

  /// Records an escape of [now]'s morning with [reason]; returns the entry.
  static Future<Map<String, Object?>> add(
    String reason, {
    DateTime? now,
  }) async {
    final at = now ?? DateTime.now();
    final entry = <String, Object?>{
      'id': const Uuid().v4(),
      'date': isoDate(at),
      'at': isoWithOffset(at),
      'reason': reason,
    };
    final entries = [entry, ...await load()].take(carried).toList();
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(key, jsonEncode(entries));
    return entry;
  }
}
