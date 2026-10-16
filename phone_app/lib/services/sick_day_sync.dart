import 'package:crdt_sync/crdt_sync.dart';
import 'package:wake_alarm_sync/services/alarm_scheduler.dart';
import 'package:wake_alarm_sync/services/day_pool_sync.dart';
import 'package:wake_alarm_sync/services/firebase_backend.dart';
import 'package:wake_alarm_sync/services/sick_day_pool.dart';

/// Moves the sick-day pool between this phone and every other device, over
/// `sickdays-sync/devices` -- the node `sickdays sync` on the PC uses.
///
/// Every sync ends by handing the merged pool to the native ring path
/// ([AlarmScheduler.setSickDays]): that cache, not the Dart store, is what
/// `AlarmReceiver` reads when it decides whether to ring.
class SickDaySync {
  /// Creates a syncer; both seams are injectable for tests.
  SickDaySync({
    Future<RemoteStore?> Function()? openClient,
    AlarmScheduler? scheduler,
  }) : _openClient = openClient ?? openFirebase,
       _scheduler = scheduler ?? AlarmScheduler();

  final Future<RemoteStore?> Function() _openClient;
  final AlarmScheduler _scheduler;

  /// Pulls, merges and pushes [pool], then refreshes the native cache.
  /// Never throws; see [syncDayPoolLog].
  Future<String> sync(SickDayPool pool) => syncDayPoolLog(
    openClient: _openClient,
    deviceId: pool.deviceId,
    pathPrefix: SickDayPool.pathPrefix,
    filename: SickDayPool.filename,
    commitMessage: 'sickdays: update pool',
    snapshot: pool.snapshot,
    replaceAll: pool.replaceAll,
    publish: () => publishToNative(pool),
    logName: 'SickDaySync',
  );

  /// Writes the pool's sick dates where `AlarmReceiver` can read them.
  Future<void> publishToNative(SickDayPool pool) => publishQuietly(
    () => _scheduler.setSickDays(pool.sickIsoDates()),
    logName: 'SickDaySync',
  );
}
