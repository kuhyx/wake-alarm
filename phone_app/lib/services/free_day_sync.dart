import 'package:crdt_sync/crdt_sync.dart';
import 'package:wake_alarm_sync/services/alarm_scheduler.dart';
import 'package:wake_alarm_sync/services/day_pool_sync.dart';
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
  /// Never throws; see [syncDayPoolLog]. The native cache is refreshed even
  /// when the sync could not run, so a day marked offline still stands the
  /// phone down.
  Future<String> sync(FreeDayPool pool) => syncDayPoolLog(
    openClient: _openClient,
    deviceId: pool.deviceId,
    pathPrefix: FreeDayPool.pathPrefix,
    filename: FreeDayPool.filename,
    commitMessage: 'freedays: update pool',
    snapshot: pool.snapshot,
    replaceAll: pool.replaceAll,
    publish: () => publishToNative(pool),
    logName: 'FreeDaySync',
  );

  /// Writes the pool's free dates where `AlarmReceiver` can read them.
  Future<void> publishToNative(FreeDayPool pool) => publishQuietly(
    () => _scheduler.setFreeDays(pool.freeIsoDates()),
    logName: 'FreeDaySync',
  );
}
