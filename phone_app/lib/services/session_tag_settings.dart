import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

/// The rooms the morning session walks through, one NFC tag each.
enum SessionTagSlot {
  /// By the scale and the shower; tapped twice, before and after.
  bathroom,

  /// Where the clothes are.
  wardrobe,

  /// Where the day starts — the PC.
  desk,
}

/// Persisted morning-session configuration: one tag per [SessionTagSlot].
///
/// Separate from `RoomProofSettings`: those two tags gate the *ring*, these
/// three gate what comes after it. A slot may hold the same physical tag as
/// a ring slot (the bathroom tag is often ring tag 2), but the three session
/// slots must be distinct from each other — one tag satisfying two rooms
/// removes the walk between them.
///
/// A slot left empty is not an error: the session skips that leg. That is
/// what makes the feature usable on the first morning after the update,
/// before any of the three has been registered.
class SessionTagSettings {
  /// Creates settings from the registered tag ids, one per slot.
  const SessionTagSettings({
    this.tagIds = const <String>['', '', ''],
    this.editedAt = '',
  });

  /// SharedPreferences key holding the tag ids as a JSON list.
  static const String kTagsKey = 'session.tagIds';

  /// SharedPreferences key holding when the tags were last changed (ISO).
  ///
  /// The stamp the cross-device merge compares (`session_sync.dart`).
  static const String kEditedAtKey = 'session.editedAt';

  /// Registered tag ids by [SessionTagSlot.index]; '' means unset.
  final List<String> tagIds;

  /// When [tagIds] was last set, ISO format, or '' when never.
  final String editedAt;

  /// The tag registered for [slot], or null when unset.
  String? tagAt(SessionTagSlot slot) {
    final id = tagIds[slot.index];
    return id.isEmpty ? null : id;
  }

  /// Which slot [tagId] is registered under, or null for an unknown tag.
  SessionTagSlot? slotOf(String tagId) {
    for (final slot in SessionTagSlot.values) {
      if (tagAt(slot) == tagId) return slot;
    }
    return null;
  }

  /// Whether any slot is registered at all.
  bool get isConfigured => tagIds.any((id) => id.isNotEmpty);

  /// Normalises [raw] to exactly one entry per slot.
  static List<String> padded(List<String> raw) => List<String>.generate(
    SessionTagSlot.values.length,
    (i) => i < raw.length ? raw[i] : '',
  );

  /// Loads the stored configuration.
  static Future<SessionTagSettings> load() async {
    final prefs = await SharedPreferences.getInstance();
    final stored = prefs.getString(kTagsKey);
    if (stored == null) return const SessionTagSettings();
    return SessionTagSettings(
      tagIds: padded(_decode(stored)),
      editedAt: prefs.getString(kEditedAtKey) ?? '',
    );
  }

  /// Decodes the stored JSON list, treating anything malformed as unset.
  static List<String> _decode(String stored) {
    try {
      final decoded = jsonDecode(stored);
      if (decoded is! List) return const <String>[];
      return decoded.whereType<String>().toList();
    } on FormatException {
      return const <String>[];
    }
  }

  /// Stores [tagId] in [slot], leaving the others untouched, stamped now.
  static Future<void> saveTagAt(SessionTagSlot slot, String tagId) async {
    final current = await load();
    final next = List<String>.of(current.tagIds);
    next[slot.index] = tagId;
    await replaceAll(next, DateTime.now().toIso8601String());
  }

  /// Stores [tagIds] wholesale with the given [editedAt].
  ///
  /// The sync merge uses this to apply a winner from another install with
  /// that side's real edit time, so the next merge does not push it back.
  static Future<void> replaceAll(List<String> tagIds, String editedAt) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(kTagsKey, jsonEncode(padded(tagIds)));
    await prefs.setString(kEditedAtKey, editedAt);
  }
}
