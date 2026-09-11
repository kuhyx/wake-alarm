import 'dart:developer' as developer;

import 'package:crdt_sync/crdt_sync.dart';
import 'package:wake_alarm_sync/services/alarm_scheduler.dart';
import 'package:wake_alarm_sync/services/firebase_backend.dart';
import 'package:wake_alarm_sync/services/free_day_pool.dart';

/// Moves the free-day pool between this phone and every other device.
///
/// Firebase only. The alarm record keeps its GitHub mirror because that
/// fallback is load-bearing for un-migrated installs; this namespace is new
/// and has no such history, so it gets no second transport.
///
/// Every sync ends by handing the merged pool to the native ring path
/// ([AlarmScheduler.setFreeDays]) — that cache, not the Dart store, is what
/// decides whether the phone rings, so it must never lag a sync.
class FreeDaySync {
  /// Creates a syncer; both seams are injectable for tests.
  FreeDaySync({
    Future<RemoteStore?> Function()? openClient,
    AlarmScheduler? scheduler,
  }) : _openClient = openClient ?? openFirebase,
       _scheduler = scheduler ?? AlarmScheduler();

  final Future<RemoteStore?> Function() _openClient;
  final AlarmScheduler _scheduler;

  /// Pulls, merges and pushes [pool], then refreshes the native cache.
  ///
  /// Returns a status line for the screen. Never throws: this also runs
  /// unattended at launch, where a dead network must degrade to a message.
  /// The native cache is refreshed even when the sync could not run, so a
  /// day marked offline still stands the phone down.
  Future<String> sync(FreeDayPool pool) async {
    final RemoteStore? client;
    try {
      client = await _openClient();
    } on Object catch (error, stackTrace) {
      developer.log(
        'free-day sync: could not open Firebase',
        name: 'FreeDaySync',
        error: error,
        stackTrace: stackTrace,
      );
      await publishToNative(pool);
      return 'Error: $error';
    }
    if (client == null) {
      await publishToNative(pool);
      return 'Not synced — connect Firebase in Settings.';
    }
    try {
      final merged = await syncLog(
        client: client,
        deviceId: pool.deviceId,
        pathPrefix: FreeDayPool.pathPrefix,
        filename: FreeDayPool.filename,
        localLog: pool.snapshot(),
        encode: logToJson,
        decode: logFromJson,
        commitMessage: 'freedays: update pool',
      );
      await pool.replaceAll(merged);
      return 'Synced ✓';
    } on Exception catch (e) {
      return 'Error: $e';
    } finally {
      await publishToNative(pool);
    }
  }

  /// Writes the pool's free dates where `AlarmReceiver` can read them.
  ///
  /// Swallows a missing platform (widget tests, a probe entry point): the
  /// Dart pool is still correct, and the cache is rewritten on the next
  /// launch anyway.
  Future<void> publishToNative(FreeDayPool pool) async {
    try {
      await _scheduler.setFreeDays(pool.freeIsoDates());
    } on Object catch (error) {
      developer.log(
        'free-day cache not written: $error',
        name: 'FreeDaySync',
        error: error,
      );
    }
  }
}
