import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';
import 'package:wake_alarm_sync/services/morning_session.dart';
import 'package:wake_alarm_sync/services/session_json.dart';

/// Persistence for the morning session: the live one and the last month.
///
/// Written after every change (see `MorningSession`): the session screen is
/// not guaranteed to survive its own thirty minutes, and a re-ring replaces
/// the whole Flutter engine. The history is what the home screen shows and
/// what the synced record carries.
class SessionStore {
  /// Creates a store; [prefs] is injectable for tests.
  SessionStore({this.prefs});

  /// SharedPreferences key holding today's session as JSON.
  static const String kCurrentKey = 'session.current';

  /// SharedPreferences key holding finished sessions, newest first.
  static const String kHistoryKey = 'session.history';

  /// Finished sessions kept locally.
  static const int keep = 30;

  /// The backing store, opened lazily when not injected.
  SharedPreferences? prefs;

  Future<SharedPreferences> get _store async =>
      prefs ??= await SharedPreferences.getInstance();

  /// The live session, or null when there is none.
  Future<MorningSession?> loadCurrent() async {
    final prefs = await _store;
    return _decodeOne(prefs.getString(kCurrentKey));
  }

  /// Persists [session] as the live one.
  Future<void> save(MorningSession session) async {
    final prefs = await _store;
    await prefs.setString(kCurrentKey, jsonEncode(session.toJson()));
  }

  /// Moves [session] into the history and clears the live slot.
  ///
  /// Replaces any history entry for the same date: a second session on one
  /// day (a probe, a re-ring after a finish) is the newer truth.
  Future<void> archive(MorningSession session) async {
    final prefs = await _store;
    final next = <MorningSession>[
      session,
      ...(await history()).where((s) => s.date != session.date),
    ];
    await _writeHistory(prefs, next);
    await prefs.remove(kCurrentKey);
  }

  /// Finished sessions, newest first.
  Future<List<MorningSession>> history() async {
    final prefs = await _store;
    return decodeHistory(prefs.getString(kHistoryKey));
  }

  /// The most recent confirmed weight, or null when never weighed.
  Future<double?> lastWeightKg() async {
    for (final session in await history()) {
      final kg = session.weightKg;
      if (kg != null) return kg;
    }
    return null;
  }

  /// Merges [remote] sessions into the history; the newer `updatedAt` wins
  /// per date.
  ///
  /// The restore path for a reinstall, and how two installs' mornings end up
  /// in one list. Returns whether anything changed.
  Future<bool> mergeHistory(List<MorningSession> remote) async {
    final prefs = await _store;
    final byDate = <String, MorningSession>{
      for (final s in await history()) s.date: s,
    };
    var changed = false;
    for (final s in remote) {
      final local = byDate[s.date];
      if (local == null || s.updatedAt.isAfter(local.updatedAt)) {
        byDate[s.date] = s;
        changed = true;
      }
    }
    if (!changed) return false;
    final merged = byDate.values.toList()
      ..sort((a, b) => b.date.compareTo(a.date));
    await _writeHistory(prefs, merged);
    return true;
  }

  Future<void> _writeHistory(
    SharedPreferences prefs,
    List<MorningSession> sessions,
  ) => prefs.setString(
    kHistoryKey,
    jsonEncode(sessions.take(keep).map((s) => s.toJson()).toList()),
  );

  static MorningSession? _decodeOne(String? raw) {
    if (raw == null) return null;
    try {
      return sessionFromJson(jsonDecode(raw));
    } on FormatException {
      return null;
    }
  }

  /// Decodes a JSON list of sessions, dropping anything malformed.
  static List<MorningSession> decodeHistory(String? raw) {
    if (raw == null) return const <MorningSession>[];
    try {
      return decodeSessions(jsonDecode(raw));
    } on FormatException {
      return const <MorningSession>[];
    }
  }

  /// Decodes an already-parsed list of session maps.
  static List<MorningSession> decodeSessions(Object? decoded) {
    if (decoded is! List) return const <MorningSession>[];
    return decoded.map(sessionFromJson).nonNulls.toList();
  }
}
