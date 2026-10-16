import 'dart:developer' as developer;
import 'dart:ui' show DartPluginRegistrant;

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:wake_alarm_sync/services/free_day_pool.dart';
import 'package:wake_alarm_sync/services/free_day_sync.dart';
import 'package:wake_alarm_sync/services/sick_day_pool.dart';
import 'package:wake_alarm_sync/services/sick_day_sync.dart';

/// Channel `PoolSyncEngine.kt` listens on for `done`.
const poolSyncChannelName = 'com.kuhy.wake_alarm_sync/poolsync';

/// Pulls both day pools and rewrites both native ring-path caches.
///
/// The two run side by side: the pre-alarm sync may only have Doze's short
/// network window. Silent, and never throws -- each failure is logged and
/// swallowed, and an unreadable pool leaves the cache as it was (the alarm
/// rings on anything it cannot read).
Future<void> refreshDayPools({
  Future<FreeDayPool> Function()? openFree,
  Future<SickDayPool> Function()? openSick,
  FreeDaySync? freeSync,
  SickDaySync? sickSync,
}) async {
  Future<void> guarded(String pool, Future<void> Function() run) async {
    try {
      await run();
    } on Exception catch (e, stack) {
      developer.log(
        '$pool pool unavailable: $e',
        name: 'WakeAlarmSync',
        error: e,
        stackTrace: stack,
      );
    }
  }

  await Future.wait([
    guarded('free-day', () async {
      final pool = await (openFree ?? FreeDayPool.open)();
      await (freeSync ?? FreeDaySync()).sync(pool);
    }),
    guarded('sick-day', () async {
      final pool = await (openSick ?? SickDayPool.open)();
      await (sickSync ?? SickDaySync()).sync(pool);
    }),
  ]);
}

/// The pre-alarm headless engine's whole job: [refreshDayPools], then say
/// `done` -- whatever happened, or the native side keeps the engine (and
/// the broadcast it holds open) until its timeout.
///
/// Started natively by `PoolSyncReceiver` (`poolSyncMain` in `main.dart`)
/// in the evening and shortly before the alarm, so a day marked on the PC
/// reaches the ring path without the app being opened.
Future<void> runHeadlessPoolSync({
  Future<void> Function()? refresh,
  MethodChannel? channel,
}) async {
  WidgetsFlutterBinding.ensureInitialized();
  // A non-`main` entrypoint does not register Dart-side plugin
  // implementations (path_provider, secure storage) by itself.
  DartPluginRegistrant.ensureInitialized();
  try {
    await (refresh ?? refreshDayPools)();
  } finally {
    try {
      await (channel ?? const MethodChannel(poolSyncChannelName))
          .invokeMethod<void>('done');
    } on Object catch (e) {
      developer.log('pool-sync done not delivered: $e', name: 'WakeAlarmSync');
    }
  }
}
