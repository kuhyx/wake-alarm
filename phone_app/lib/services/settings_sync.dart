/// The NFC tags and home location, carried on the synced alarm record.
///
/// Both used to live only in SharedPreferences, so a reinstall lost them and
/// the user re-registered two tags and re-captured home by hand (2026-09-11).
/// They are properties of the flat, not of one install, so they ride on the
/// same `alarm.json` record the PC already reads -- as extra per-field
/// entries the PC parser ignores -- and a fresh install gets them back on its
/// first sync with a backend connected.
///
/// Last-writer-wins per field, by wall time: a registration on any install
/// beats an older one anywhere else. The stamp is the local `editedAt`
/// (`RoomProofSettings` / `HomeLocationSettings`) turned into a deterministic
/// [Hlc], so re-syncing an unchanged value is a no-op rather than a fresh
/// push every tick -- the same trick `diet_guard`'s catering credential uses.
/// Comparisons are on wall time only: a value applied *from* the log gets the
/// log's wall time as its stamp, and comparing counters or node ids on that
/// tie would push the identical value straight back.
library;

import 'package:crdt_sync/crdt_sync.dart';
import 'package:wake_alarm_sync/services/alarm_sync_service.dart';
import 'package:wake_alarm_sync/services/home_location_settings.dart';
import 'package:wake_alarm_sync/services/room_proof_settings.dart';

/// Field holding the registered tag ids, one string per slot.
const nfcTagsField = 'nfc_tag_ids';

/// Field holding [HomeLocationSettings.toJson]; a cleared home is the
/// all-null shape, not an absent field, so clearing propagates too.
const homeLocationField = 'home_location';

/// Wall-clock milliseconds of an ISO [editedAt], or 0 when it does not parse.
int _msOf(String editedAt) =>
    DateTime.tryParse(editedAt)?.toUtc().millisecondsSinceEpoch ?? 0;

/// The stamp a value applied from the log carries locally.
String _stampOf(Hlc hlc) => DateTime.fromMillisecondsSinceEpoch(
  hlc.wallTimeMs,
  isUtc: true,
).toIso8601String();

/// Copies local edits newer than the log's copy onto the alarm record.
///
/// Run before every sync so a tag registered a minute ago is in the pushed
/// log. An install that never edited a value (empty `editedAt`) contributes
/// nothing, so it cannot clobber a peer's registration with its own blanks --
/// unless it holds a value from before stamps existed, which goes in at
/// [_legacyMs] so it is kept when nothing else is known and loses to any
/// stamped peer.
Future<void> stageLocalSettings(AlarmSyncService service) async {
  final tags = await RoomProofSettings.load();
  await _stage(
    service,
    nfcTagsField,
    tags.editedAt,
    tags.nfcTagIds,
    configured: tags.nfcTagIds.any((id) => id.isNotEmpty),
  );
  final home = await HomeLocationSettings.load();
  await _stage(
    service,
    homeLocationField,
    home.editedAt,
    home.toJson(),
    configured: home.isConfigured,
  );
}

/// The stamp of a pre-stamp value: just above the epoch, so any real edit
/// wins, but present, so it is pushed rather than silently dropped.
const _legacyMs = 1;

Future<void> _stage(
  AlarmSyncService service,
  String field,
  String editedAt,
  Object value, {
  required bool configured,
}) async {
  if (editedAt.isEmpty && !configured) return;
  final localMs = editedAt.isEmpty ? _legacyMs : _msOf(editedAt);
  final existing = service.field(field);
  if (existing != null && existing.$2.wallTimeMs >= localMs) return;
  await service.setFields({
    field: value,
  }, Hlc.newTick(service.deviceId, wallTimeMsOverride: localMs));
}

/// Writes log values newer than the local copy into SharedPreferences.
///
/// Run after every sync; this is the restore path for a fresh install. Values
/// that fail to decode are left alone: a peer's malformed push must not wipe
/// a working registration.
Future<void> applySyncedSettings(AlarmSyncService service) async {
  final tags = await RoomProofSettings.load();
  final tagField = service.field(nfcTagsField);
  if (tagField != null && _newer(tagField.$2, tags.editedAt)) {
    final ids = tagField.$1;
    if (ids is List) {
      await RoomProofSettings.replaceAll(
        ids.whereType<String>().toList(),
        _stampOf(tagField.$2),
      );
    }
  }
  final home = await HomeLocationSettings.load();
  final homeField = service.field(homeLocationField);
  if (homeField != null && _newer(homeField.$2, home.editedAt)) {
    final json = homeField.$1;
    if (json is Map) {
      await HomeLocationSettings.applySynced(
        HomeLocationSettings.fromJson(
          Map<String, dynamic>.from(json),
        ).withEditedAt(_stampOf(homeField.$2)),
      );
    }
  }
}

bool _newer(Hlc remote, String localEditedAt) =>
    localEditedAt.isEmpty || remote.wallTimeMs > _msOf(localEditedAt);
