import 'dart:io';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:crdt_sync/crdt_sync_io.dart';
import 'package:http/http.dart' as http;
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:wake_alarm_sync/services/firebase_backend.dart';

/// The alarm time this device holds, as read from or written to the store.
typedef Alarm = ({int hour, int minute});

/// Cross-device alarm sync for wake_alarm_sync, on the shared `crdt_sync`
/// transport instead of a bespoke GitHub Gist.
///
/// The phone is the **sole writer**: it stores the chosen alarm locally in a
/// [LogStore] (one HLC-stamped [Record], id [_recordId]) and pushes that log
/// to `wake-alarm-sync/devices/phone/alarm.json` — Firebase first, mirrored
/// to the private `kuhyx/syncs` repo during the cutover (see [syncBackend]).
/// The path is deliberately identical on both backends, so only the transport
/// differs.
///
/// The PC side is read-only (`wake_alarm/_sync.py`, which tries Firebase then
/// GitHub, caching the result for `shutdown-wrapper.sh`). There is no
/// pull/merge here: the phone is the only writer, so its local store is
/// always the source of truth.
class AlarmSyncService {
  /// Wraps an already-loaded log store.
  AlarmSyncService(this._store);

  final LogStore _store;

  /// Fixed sync target: the shared private repo used by every companion app.
  static const owner = 'kuhyx';

  /// Repo name within [owner] that holds every app's `*-sync/` data.
  static const repo = 'syncs';

  /// This device's id in the `devices/<id>/` layout. The phone is the only
  /// writer, so a constant id is enough (HLCs still order re-installs).
  static const deviceId = 'phone';

  static const _remotePath = 'wake-alarm-sync/devices/$deviceId/alarm.json';
  static const _recordId = 'alarm';
  static const _hourField = 'alarm_hour';
  static const _minuteField = 'alarm_minute';

  /// Opens the on-disk alarm store.
  ///
  /// [persistence] is injectable so tests can supply an in-memory backend
  /// instead of touching the real app-documents directory.
  static Future<AlarmSyncService> open({LogPersistence? persistence}) async {
    final backend = persistence ?? await _defaultPersistence();
    final store = LogStore(persistence: backend, nodeId: deviceId);
    await store.load();
    return AlarmSyncService(store);
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

  /// Stores [hour]:[minute] locally, stamped with a fresh monotonic HLC.
  ///
  /// Both fields share one clock tick — they are always set together, so a
  /// concurrent per-field merge would never split them.
  Future<void> setLocal(int hour, int minute) async {
    final hlc = _store.nextHlc();
    await _store.upsert(
      Record(
        id: _recordId,
        fields: {_hourField: (hour, hlc), _minuteField: (minute, hlc)},
      ),
    );
  }

  /// Pushes the local alarm log using [client].
  ///
  /// Takes a [RemoteStore] rather than a `GitHubClient` so the same call
  /// serves Firebase, GitHub, or the [MirrorStore] that writes both — the
  /// backend is chosen once, in [syncBackend].
  Future<void> pushWith(RemoteStore client) => client.putFileText(
    _remotePath,
    logToJson(_store.snapshot()),
    message: 'wake_alarm_sync: update alarm',
  );

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
