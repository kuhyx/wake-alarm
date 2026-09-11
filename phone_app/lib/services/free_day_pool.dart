import 'dart:io';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:crdt_sync/crdt_sync_io.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:wake_alarm_sync/services/alarm_sync_service.dart';

/// The shared free-day pool, as the phone sees it.
///
/// A Dart port of `~/src/utils/freedays` (Python), which owns the rules: one
/// global pool for every gate app, 35 days per calendar year resetting on
/// Jan 1, declared for today or later and never backdated, releasing refunds
/// only a day that has not arrived, and `consumed` is sticky. The record
/// shape is byte-identical to the Python package's so both sides merge one
/// log: the record id *is* the ISO date, and un-marking flips `state` rather
/// than tombstoning, because crdt tombstones are monotonic and a deleted date
/// could never be marked again.
///
/// Nothing here touches the network. `free_day_sync.dart` does that, and the
/// Kotlin ring path reads a cache this pool exports, so an offline phone
/// still stands down on a day it marked itself.
class FreeDayPool {
  /// Wraps an already-loaded store writing as [deviceId].
  FreeDayPool(this._store, {required this.deviceId});

  final LogStore _store;

  /// The device uuid stamped as `actor` on every write.
  final String deviceId;

  /// Days granted per calendar year. Mirrors `DEFAULT_ANNUAL_BUDGET`.
  static const annualBudget = 35;

  /// Remote layout shared with the Python package: `<prefix>/<device>/<file>`.
  static const pathPrefix = 'freedays-sync/devices';

  /// The per-device file name under [pathPrefix].
  static const filename = 'free_days.json';

  static const _stateField = 'state';
  static const _consumedField = 'consumed';
  static const _actorField = 'actor';
  static const _reasonField = 'reason';
  static const _free = 'free';
  static const _cleared = 'cleared';

  /// Opens the on-disk pool, minting the device id the alarm store uses.
  ///
  /// Same uuid as [AlarmSyncService] on purpose: one install is one actor
  /// in every namespace it writes to.
  static Future<FreeDayPool> open({
    LogPersistence? persistence,
    String? deviceId,
  }) async {
    final backend = persistence ?? await _defaultPersistence();
    final id = deviceId ?? await AlarmSyncService.loadDeviceId();
    final store = LogStore(persistence: backend, nodeId: id);
    await store.load();
    return FreeDayPool(store, deviceId: id);
  }

  static Future<LogPersistence> _defaultPersistence() async {
    final dir = await getApplicationDocumentsDirectory();
    return FileLogPersistence(File(p.join(dir.path, 'free_days_log.json')));
  }

  /// Today as a local calendar date, midnight-truncated.
  ///
  /// Local, never UTC: a free day is a human calendar day, and the Python
  /// side decides the same way (`_day.today()`).
  static DateTime today() => dateOnly(DateTime.now());

  /// [when] with its time-of-day dropped, in local time.
  static DateTime dateOnly(DateTime when) =>
      DateTime(when.year, when.month, when.day);

  /// `yyyy-MM-dd`, the record id.
  static String toIso(DateTime day) {
    final m = day.month.toString().padLeft(2, '0');
    final d = day.day.toString().padLeft(2, '0');
    return '${day.year}-$m-$d';
  }

  /// Parses a record id back to a date, or null when it is not one.
  static DateTime? parseIso(String id) {
    final match = RegExp(r'^(\d{4})-(\d{2})-(\d{2})$').firstMatch(id);
    if (match == null) return null;
    final parsed = DateTime(
      int.parse(match[1]!),
      int.parse(match[2]!),
      int.parse(match[3]!),
    );
    // DateTime normalises 2026-02-30 to March 2 silently; reject that.
    return toIso(parsed) == id ? parsed : null;
  }

  /// The whole log, for `syncLog`.
  Log snapshot() => _store.snapshot();

  /// Replaces the log with a merged result and persists it.
  Future<void> replaceAll(Log merged) => _store.replaceAll(merged);

  static bool _isFree(Record? record) {
    if (record == null || record.deleted) return false;
    return record.fields[_stateField]?.$1 == _free;
  }

  static bool _isConsumed(Record? record) =>
      record?.fields[_consumedField]?.$1 == true;

  /// Whether the gates stand down on [day].
  ///
  /// Answers false for anything it does not understand: an unreadable pool
  /// means the normal rules apply, never that everything is switched off.
  bool isFree(DateTime day) => _isFree(_store.get(toIso(dateOnly(day))));

  /// The reason stored for [day], or an empty string.
  String reasonFor(DateTime day) {
    final value = _store.get(toIso(dateOnly(day)))?.fields[_reasonField]?.$1;
    return value is String ? value : '';
  }

  /// Every currently-free date, ascending.
  List<DateTime> freeDays() {
    final days = <DateTime>[
      for (final record in _store.values)
        if (_isFree(record)) ?parseIso(record.id),
    ];
    return days..sort();
  }

  /// Every ISO date currently free, for the native ring-path cache.
  List<String> freeIsoDates() => freeDays().map(toIso).toList();

  /// How many of [year]'s days are gone: still free, or released after they
  /// had already arrived. Taking Monday off and clearing it on Tuesday does
  /// not give Monday back.
  int spent(int year) {
    var count = 0;
    for (final record in _store.values) {
      final day = parseIso(record.id);
      if (day == null || day.year != year) continue;
      if (_isFree(record) || _isConsumed(record)) count++;
    }
    return count;
  }

  /// Days left in [year], never below zero.
  int remaining(int year) {
    final left = annualBudget - spent(year);
    return left < 0 ? 0 : left;
  }

  /// Marks [day] free, everywhere, for every app.
  ///
  /// Throws [FreeDayPolicyError] for a past day, an already-free day, or an
  /// exhausted year. [now] is injectable for tests.
  Future<void> mark(DateTime day, {String reason = '', DateTime? now}) async {
    final target = dateOnly(day);
    final reference = dateOnly(now ?? DateTime.now());
    final id = toIso(target);
    if (target.isBefore(reference)) {
      throw FreeDayPolicyError(
        '$id has already passed — free days are declared, not backdated.',
      );
    }
    final existing = _store.get(id);
    if (_isFree(existing)) {
      throw FreeDayPolicyError('$id is already a free day.');
    }
    if (remaining(target.year) <= 0) {
      throw FreeDayPolicyError(
        'No free days left in ${target.year} — all $annualBudget are spent.',
      );
    }
    // Sticky: a day that has arrived, or was ever spent, stays spent.
    final consumed = _isConsumed(existing) || !target.isAfter(reference);
    await _write(id, free: true, consumed: consumed, reason: reason);
  }

  /// Gives [day] back; refunds it only if it has not arrived yet.
  ///
  /// Throws [FreeDayPolicyError] when [day] is not currently free.
  Future<void> release(DateTime day, {DateTime? now}) async {
    final target = dateOnly(day);
    final reference = dateOnly(now ?? DateTime.now());
    final id = toIso(target);
    final existing = _store.get(id);
    if (!_isFree(existing)) {
      throw FreeDayPolicyError('$id is not a free day.');
    }
    final consumed = _isConsumed(existing) || !target.isAfter(reference);
    await _write(id, free: false, consumed: consumed, reason: '');
  }

  /// Every field shares one tick, so a concurrent mark and release of one
  /// day resolve together rather than interleaving state from one device
  /// with a reason from the other.
  Future<void> _write(
    String id, {
    required bool free,
    required bool consumed,
    required String reason,
  }) async {
    final hlc = _store.nextHlc();
    await _store.upsert(
      Record(
        id: id,
        fields: {
          _stateField: (free ? _free : _cleared, hlc),
          _consumedField: (consumed, hlc),
          _actorField: (deviceId, hlc),
          _reasonField: (reason, hlc),
        },
      ),
    );
  }
}

/// A mark or release the pool's rules refuse. The message is for the user.
class FreeDayPolicyError implements Exception {
  /// Creates the refusal with its user-facing [message].
  FreeDayPolicyError(this.message);

  /// Why the pool said no.
  final String message;

  @override
  String toString() => message;
}
