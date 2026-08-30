import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

/// Persisted room-proof configuration: the two registered NFC tags.
///
/// Two tags, in two different places, are what force the walk. Registering
/// fewer than [requiredTagCount] does not weaken the sequence into something
/// easier — it makes the NFC stages unsatisfiable, which is why the ring
/// screen drops straight to the bypass when [isComplete] is false.
class RoomProofSettings {
  /// Creates settings from the registered tag ids, one per slot.
  const RoomProofSettings({this.nfcTagIds = const <String>['', '']});

  /// SharedPreferences key holding the tag ids as a JSON list.
  static const String kNfcTagsKey = 'roomProof.nfcTagIds';

  /// The pre-two-tag key, migrated into slot 0 on first load.
  static const String kLegacyNfcTagKey = 'roomProof.nfcTagId';

  /// How many tags the strict sequence needs.
  static const int requiredTagCount = 2;

  /// Registered tag ids by slot; an empty string means that slot is unset.
  ///
  /// Always [requiredTagCount] long, so slot writes never have to grow it.
  final List<String> nfcTagIds;

  /// The tag registered for [slot], or null when that slot is unset.
  String? tagAt(int slot) {
    if (slot < 0 || slot >= nfcTagIds.length) return null;
    final id = nfcTagIds[slot];
    return id.isEmpty ? null : id;
  }

  /// Whether every slot holds a distinct tag, so the sequence is satisfiable.
  ///
  /// Distinctness matters: two slots holding the same id would let one tap
  /// satisfy both stages, collapsing the walk this whole gate exists to force.
  bool get isComplete {
    final ids = <String>{};
    for (var slot = 0; slot < requiredTagCount; slot++) {
      final id = tagAt(slot);
      if (id == null || !ids.add(id)) return false;
    }
    return true;
  }

  /// Normalises [raw] to exactly [requiredTagCount] slots.
  static List<String> _padded(List<String> raw) => List<String>.generate(
    requiredTagCount,
    (i) => i < raw.length ? raw[i] : '',
  );

  /// Loads the stored configuration, migrating a single legacy tag if present.
  static Future<RoomProofSettings> load() async {
    final prefs = await SharedPreferences.getInstance();
    final stored = prefs.getString(kNfcTagsKey);
    if (stored != null) {
      return RoomProofSettings(nfcTagIds: _padded(_decode(stored)));
    }
    // One-time migration: an existing install has a tag registered under the
    // old key, and silently losing it would leave the user unable to dismiss
    // by the normal path on the first morning after the update.
    final legacy = prefs.getString(kLegacyNfcTagKey);
    return RoomProofSettings(
      nfcTagIds: _padded(<String>[?legacy]),
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

  /// Stores [tagId] in [slot], leaving the other slot untouched.
  static Future<void> saveNfcTagAt(int slot, String tagId) async {
    final current = await load();
    final next = List<String>.of(current.nfcTagIds);
    if (slot < 0 || slot >= next.length) return;
    next[slot] = tagId;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(kNfcTagsKey, jsonEncode(next));
  }
}
