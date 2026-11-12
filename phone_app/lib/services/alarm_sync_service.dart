import 'dart:io';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:crdt_sync/crdt_sync_io.dart';
import 'package:http/http.dart' as http;
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uuid/uuid.dart';
import 'package:wake_alarm_sync/services/alarm_sync_e2e.dart';
import 'package:wake_alarm_sync/services/firebase_backend.dart';

/// The alarm time this device holds, as read from or written to the store.
typedef Alarm = ({int hour, int minute});

/// Cross-device alarm sync for wake_alarm_sync, on the shared `crdt_sync`
/// transport instead of a bespoke GitHub Gist.
///
/// The phone is the **sole writer**: it stores the chosen alarm locally in a
/// [LogStore] (one HLC-stamped [Record], id [_recordId]) and pushes that log
/// to `wake-alarm-sync/devices-e2e/<deviceId>/alarm.json`, end-to-end
/// encrypted (`alarm_sync_e2e.dart`) — Firebase first,
/// mirrored to the private `kuhyx/syncs` repo during the cutover (see
/// [syncBackend]). The path is deliberately identical on both backends, so
/// only the transport differs.
///
/// [deviceId] is a per-install uuid, not the fixed `phone` constant this app
/// shipped with ([legacyDeviceId]). The PC reader lists device directories
/// and ranks their logs by HLC rather than reading one hardcoded path, so a
/// migrating install is picked up automatically and the newest alarm wins
/// regardless of which directory it landed in.
///
/// The PC side is read-only (`wake_alarm/_sync.py`, which tries Firebase then
/// GitHub). The phone does pull and merge, though — not for the alarm time,
/// which it always owns, but for the NFC tags and home location that ride on
/// the same record (`settings_sync.dart`): a reinstalled phone gets them back
/// from whichever previous install pushed them last.
class AlarmSyncService {
  /// Wraps an already-loaded log store pushing under [deviceId].
  AlarmSyncService(this._store, {required this.deviceId});

  final LogStore _store;

  /// Fixed sync target: the shared private repo used by every companion app.
  static const owner = 'kuhyx';

  /// Repo name within [owner] that holds every app's `*-sync/` data.
  static const repo = 'syncs';

  /// The device id this install used before migrating to a persisted uuid.
  ///
  /// The PC reader still reads `devices/<legacyDeviceId>/` as a last resort,
  /// so an install that has not migrated keeps working; see
  /// `wake_alarm/_constants.py`'s `SYNC_ALARM_PATH`.
  static const legacyDeviceId = 'phone';

  /// SharedPreferences key holding this install's persisted device id.
  ///
  /// Named to match the sibling apps (`todo`, `home_inventory`), which store
  /// the same thing under the same key.
  static const kDeviceIdKey = 'crdt.nodeId';

  /// This device's id in the `devices/<id>/` layout.
  ///
  /// A per-install uuid rather than the old fixed `phone` constant: two
  /// installs sharing an id overwrite each other's pushed file on every
  /// tick, and a reinstall would silently inherit the previous install's
  /// CRDT identity. The PC reader discovers device directories, so it finds
  /// whatever uuid this turns out to be.
  final String deviceId;

  static const _recordId = 'alarm';
  static const _hourField = 'alarm_hour';
  static const _minuteField = 'alarm_minute';

  /// Returns this install's device id, minting and persisting one if absent.
  ///
  /// Migrating installs keep publishing real alarms throughout: the id only
  /// changes which directory the push lands in, and the PC ranks every
  /// device's log by HLC, so the newest alarm wins whichever path it is under.
  static Future<String> loadDeviceId() async {
    final prefs = await SharedPreferences.getInstance();
    final existing = prefs.getString(kDeviceIdKey);
    if (existing != null && existing.isNotEmpty) return existing;
    final minted = const Uuid().v4();
    await prefs.setString(kDeviceIdKey, minted);
    return minted;
  }

  /// Opens the on-disk alarm store.
  ///
  /// [persistence] is injectable so tests can supply an in-memory backend
  /// instead of touching the real app-documents directory. [deviceId] is
  /// injectable for the same reason; production resolves it via
  /// [loadDeviceId].
  static Future<AlarmSyncService> open({
    LogPersistence? persistence,
    String? deviceId,
  }) async {
    final backend = persistence ?? await _defaultPersistence();
    final id = deviceId ?? await loadDeviceId();
    final store = LogStore(persistence: backend, nodeId: id);
    await store.load();
    return AlarmSyncService(store, deviceId: id);
  }

  static Future<LogPersistence> _defaultPersistence() async {
    final dir = await getApplicationDocumentsDirectory();
    return FileLogPersistence(File(p.join(dir.path, 'alarm_log.json')));
  }

  /// The alarm currently stored locally, or `null` if none is set yet.
  Alarm? get currentAlarm {
    final record = _store.get(_recordId);
    if (record == null || record.deleted) return null;
    final hour = record.fields[_hourField]?.$1;
    final minute = record.fields[_minuteField]?.$1;
    if (hour is int && minute is int) return (hour: hour, minute: minute);
    return null;
  }

  /// The whole log, for the user-facing export.
  Log snapshot() => _store.snapshot();

  /// Replaces the log with a merged result and persists it (import).
  Future<void> replaceAll(Log merged) => _store.replaceAll(merged);

  /// Stores [hour]:[minute] locally, stamped with a fresh monotonic HLC.
  ///
  /// Both fields share one clock tick — they are always set together, so a
  /// concurrent per-field merge would never split them.
  Future<void> setLocal(int hour, int minute) =>
      setFields({_hourField: hour, _minuteField: minute}, _store.nextHlc());

  /// Upserts [values] onto the alarm record at [hlc], keeping every other
  /// field.
  ///
  /// Preserving is the point: the record also carries the synced settings
  /// (`settings_sync.dart`), and a whole-record replace on every publish
  /// would silently drop them from the pushed log.
  Future<void> setFields(Map<String, Object?> values, Hlc hlc) async {
    final existing = _store.get(_recordId);
    await _store.upsert(
      Record(
        id: _recordId,
        fields: {
          ...?existing?.fields,
          for (final e in values.entries) e.key: (e.value, hlc),
        },
      ),
    );
  }

  /// The value and clock of [field] on the alarm record, or null when unset.
  (Object?, Hlc)? field(String field) => _store.get(_recordId)?.fields[field];

  /// Syncs the local alarm log through [client]: pulls every other device's
  /// log, merges per field by HLC, then pushes the result.
  ///
  /// Takes a [RemoteStore] rather than a `GitHubClient` so the same call
  /// serves Firebase, GitHub, or the [MirrorStore] that writes both — the
  /// backend is chosen once, in [syncBackend].
  ///
  /// The pull is what brings the tags and home location back to a fresh
  /// install. The alarm time itself is unaffected: [setLocal] runs first on
  /// every publish, so the local time is always the newest and wins.
  ///
  /// Everything goes through the end-to-end encrypted view of [client]
  /// (`alarm_sync_e2e.dart`); a locked device throws [SyncLockedException]
  /// before reading or writing anything.
  Future<void> pushWith(RemoteStore client) async {
    final sealed = await openAlarmStore(client);
    final merged = await syncLog(
      client: sealed,
      deviceId: deviceId,
      pathPrefix: alarmLayout.prefix,
      revsPath: alarmLayout.revsPath,
      filename: 'alarm.json',
      localLog: _store.snapshot(),
      encode: logToJson,
      decode: logFromJson,
      commitMessage: 'wake_alarm_sync: update alarm',
      legacyDeviceId: legacyDeviceId,
    );
    await _store.replaceAll(merged);
  }

  /// Pushes to Firebase when this device is set up for it, mirroring to
  /// GitHub during the cutover; to GitHub alone when it is not.
  ///
  /// [token] still authenticates the GitHub half, so an un-migrated phone
  /// behaves exactly as before.
  Future<void> push(String token, {http.Client? httpClient}) async {
    final github = GitHubClient(
      owner: owner,
      repo: repo,
      token: token,
      httpClient: httpClient,
    );
    await pushWith(await syncBackend(github));
  }
}
