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
  const RoomProofSettings({
    this.nfcTagIds = const <String>['', ''],
    this.editedAt = '',
  });

  /// SharedPreferences key holding the tag ids as a JSON list.
  static const String kNfcTagsKey = 'roomProof.nfcTagIds';

  /// The pre-two-tag key, migrated into slot 0 on first load.
  static const String kLegacyNfcTagKey = 'roomProof.nfcTagId';

  /// SharedPreferences key holding when the tags were last changed (ISO).
  ///
  /// This is the stamp the cross-device merge compares (`settings_sync.dart`),
  /// so a registration here beats an older one from a previous install and
  /// vice versa. Empty means never edited on this install.
  static const String kEditedAtKey = 'roomProof.editedAt';

  /// How many tags the strict sequence needs.
  static const int requiredTagCount = 2;

  /// Registered tag ids by slot; an empty string means that slot is unset.
  ///
  /// Always [requiredTagCount] long, so slot writes never have to grow it.
  final List<String> nfcTagIds;

  /// When [nfcTagIds] was last set, ISO format, or '' when never.
  final String editedAt;

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
      return RoomProofSettings(
        nfcTagIds: _padded(_decode(stored)),
        editedAt: prefs.getString(kEditedAtKey) ?? '',
      );
    }
    // One-time migration: an existing install has a tag registered under the
    // old key, and silently losing it would leave the user unable to dismiss
    // by the normal path on the first morning after the update.
    final legacy = prefs.getString(kLegacyNfcTagKey);
    return RoomProofSettings(nfcTagIds: _padded(<String>[?legacy]));
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

  /// Stores [tagId] in [slot], leaving the other slot untouched, stamped now.
  static Future<void> saveNfcTagAt(int slot, String tagId) async {
    final current = await load();
    final next = List<String>.of(current.nfcTagIds);
    if (slot < 0 || slot >= next.length) return;
    next[slot] = tagId;
    await replaceAll(next, DateTime.now().toIso8601String());
  }

  /// Stores [tagIds] wholesale with the given [editedAt].
  ///
  /// The sync merge uses this to apply a winner from another install, keeping
  /// that side's real edit time rather than "now" -- otherwise the next merge
  /// would see a fresher local stamp and push the same value straight back.
  static Future<void> replaceAll(List<String> tagIds, String editedAt) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(kNfcTagsKey, jsonEncode(_padded(tagIds)));
    await prefs.setString(kEditedAtKey, editedAt);
  }
}
