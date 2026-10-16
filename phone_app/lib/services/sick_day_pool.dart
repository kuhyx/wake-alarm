import 'dart:io';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:crdt_sync/crdt_sync_io.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:wake_alarm_sync/services/alarm_sync_service.dart';
import 'package:wake_alarm_sync/services/free_day_pool.dart';

/// The shared sick-day pool, as the phone sees it.
///
/// A Dart port of `~/src/utils/sickdays` (Python), which owns the rules:
/// every day is normal until marked sick; only today or a later day can be
/// marked or cleared; no cap, no reason, no countdown; and a free day is
/// never also a sick day. The record shape is the Python package's wire
/// format: the record id *is* the ISO date, fields `state` (`sick` /
/// `cleared`) and `actor`, both stamped with one HLC tick. Clearing flips
/// `state` rather than tombstoning, because crdt tombstones are monotonic
/// and a deleted date could never be marked sick again.
///
/// This is not the free-day pool: its own file, its own remote node
/// (`sickdays-sync/devices`), its own native cache. Nothing here touches
/// the network; `sick_day_sync.dart` does that.
class SickDayPool {
  /// Wraps an already-loaded store writing as [deviceId].
  SickDayPool(this._store, {required this.deviceId});

  final LogStore _store;

  /// The device uuid stamped as `actor` on every write.
  final String deviceId;

  /// Remote layout shared with the Python package: `<prefix>/<device>/<file>`.
  static const pathPrefix = 'sickdays-sync/devices';

  /// The per-device file name under [pathPrefix].
  static const filename = 'sick_days.json';

  static const _stateField = 'state';
  static const _actorField = 'actor';
  static const _sick = 'sick';
  static const _cleared = 'cleared';

  /// Opens the on-disk pool under the install's one device uuid (the same
  /// one the alarm and free-day stores write as).
  static Future<SickDayPool> open({
    LogPersistence? persistence,
    String? deviceId,
  }) async {
    final backend = persistence ?? await _defaultPersistence();
    final id = deviceId ?? await AlarmSyncService.loadDeviceId();
    final store = LogStore(persistence: backend, nodeId: id);
    await store.load();
    return SickDayPool(store, deviceId: id);
  }

  static Future<LogPersistence> _defaultPersistence() async {
    final dir = await getApplicationDocumentsDirectory();
    return FileLogPersistence(File(p.join(dir.path, 'sick_days_log.json')));
  }

  /// The whole log, for `syncLog`.
  Log snapshot() => _store.snapshot();

  /// Replaces the log with a merged result and persists it.
  Future<void> replaceAll(Log merged) => _store.replaceAll(merged);

  /// Anything not understood -- a tombstone, a missing or unknown state --
  /// reads as "not sick", exactly like `sickdays.is_sick_record`.
  static bool _isSick(Record? record) {
    if (record == null || record.deleted) return false;
    return record.fields[_stateField]?.$1 == _sick;
  }

  /// Whether [day] is a sick day.
  bool isSick(DateTime day) =>
      _isSick(_store.get(FreeDayPool.toIso(FreeDayPool.dateOnly(day))));

  /// Every currently-sick date, ascending.
  List<DateTime> sickDays() {
    final days = <DateTime>[
      for (final record in _store.values)
        if (_isSick(record)) ?FreeDayPool.parseIso(record.id),
    ];
    return days..sort();
  }

  /// Every ISO date currently sick, past ones included, for the native
  /// cache: the stick skips past sick days when it walks back the streak.
  List<String> sickIsoDates() => sickDays().map(FreeDayPool.toIso).toList();

  /// Marks [day] sick, everywhere, for every app.
  ///
  /// Throws [SickDayPolicyError] for a past day, a day already sick, or a
  /// day [isFree] says is in the free-day pool. [now] is injectable.
  Future<void> add(
    DateTime day, {
    required bool Function(DateTime day) isFree,
    DateTime? now,
  }) async {
    final id = _checkNotPast(day, now, 'marked');
    if (_isSick(_store.get(id))) {
      throw SickDayPolicyError('$id is already a sick day.');
    }
    if (isFree(FreeDayPool.dateOnly(day))) {
      throw SickDayPolicyError(
        '$id is a free day — release it in Free days first.',
      );
    }
    await _write(id, sick: true);
  }

  /// Clears [day] back to a normal day.
  ///
  /// Throws [SickDayPolicyError] for a past day or a day that is not sick.
  Future<void> remove(DateTime day, {DateTime? now}) async {
    final id = _checkNotPast(day, now, 'cleared');
    if (!_isSick(_store.get(id))) {
      throw SickDayPolicyError('$id is not a sick day.');
    }
    await _write(id, sick: false);
  }

  /// The ISO id of [day], or a refusal when it is before [now]'s date.
  String _checkNotPast(DateTime day, DateTime? now, String verb) {
    final target = FreeDayPool.dateOnly(day);
    final reference = FreeDayPool.dateOnly(now ?? DateTime.now());
    final id = FreeDayPool.toIso(target);
    if (target.isBefore(reference)) {
      throw SickDayPolicyError(
        '$id has already passed — only today or later can be $verb.',
      );
    }
    return id;
  }

  /// Both fields share one tick, as the Python writer does.
  Future<void> _write(String id, {required bool sick}) async {
    final hlc = _store.nextHlc();
    await _store.upsert(
      Record(
        id: id,
        fields: {
          _stateField: (sick ? _sick : _cleared, hlc),
          _actorField: (deviceId, hlc),
        },
      ),
    );
  }
}

/// An add or remove the pool's rules refuse. The message is for the user.
class SickDayPolicyError implements Exception {
  /// Creates the refusal with its user-facing [message].
  SickDayPolicyError(this.message);

  /// Why the pool said no.
  final String message;

  @override
  String toString() => message;
}
