import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wake_alarm_sync/services/alarm_scheduler.dart';
import 'package:wake_alarm_sync/services/day_pool_refresh.dart';
import 'package:wake_alarm_sync/services/free_day_pool.dart';
import 'package:wake_alarm_sync/services/free_day_sync.dart';
import 'package:wake_alarm_sync/services/sick_day_pool.dart';
import 'package:wake_alarm_sync/services/sick_day_sync.dart';

import '../fake_day_pool_store.dart';

/// The PC→phone path with the app closed: what `poolSyncMain` runs.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late Map<String, List<String>> caches;
  late AlarmScheduler scheduler;
  late List<String> done;
  const poolChannel = MethodChannel(poolSyncChannelName);

  setUp(() {
    caches = {};
    done = [];
    const channel = MethodChannel(AlarmScheduler.channelName);
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          ..setMockMethodCallHandler(channel, (call) async {
            caches[call.method] = ((call.arguments as Map)['dates'] as List)
                .cast<String>();
            return null;
          })
          ..setMockMethodCallHandler(poolChannel, (call) async {
            done.add(call.method);
            return null;
          });
    addTearDown(() => messenger.setMockMethodCallHandler(poolChannel, null));
    scheduler = AlarmScheduler(channel: channel);
  });

  test('a sick day the PC pushed to RTDB reaches the native cache', () async {
    // What `sickdays add 2026-10-20` + the PC's sync timer leave in RTDB.
    final remote = MemRemote();
    remote.files['sickdays-sync/devices/$pythonDeviceId/sick_days.json'] =
        pythonSickLog;
    final sick = await SickDayPool.open(
      persistence: MemPersistence(),
      deviceId: 'phone',
    );
    final free = await FreeDayPool.open(
      persistence: MemPersistence(),
      deviceId: 'phone',
    );

    await runHeadlessPoolSync(
      refresh: () => refreshDayPools(
        openFree: () async => free,
        openSick: () async => sick,
        freeSync: FreeDaySync(
          openClient: () async => remote,
          scheduler: scheduler,
        ),
        sickSync: SickDaySync(
          openClient: () async => remote,
          scheduler: scheduler,
        ),
      ),
    );

    expect(caches['setSickDays'], ['2026-10-20']);
    expect(caches['setFreeDays'], isEmpty);
    expect(done, ['done']);
  });

  test('a PC sick day that keeps the alarm never reaches the cache', () async {
    // `sickdays add 2026-10-22` + `sickdays keep 2026-10-22 alarm` on the PC.
    final remote = MemRemote();
    remote.files['sickdays-sync/devices/pc/sick_days.json'] = pythonKeepLog;
    await refreshDayPools(
      openFree: () =>
          FreeDayPool.open(persistence: MemPersistence(), deviceId: 'phone'),
      openSick: () =>
          SickDayPool.open(persistence: MemPersistence(), deviceId: 'phone'),
      freeSync: FreeDaySync(
        openClient: () async => remote,
        scheduler: scheduler,
      ),
      sickSync: SickDaySync(
        openClient: () async => remote,
        scheduler: scheduler,
      ),
    );
    expect(caches['setSickDays'], ['2026-10-20', '2026-10-23']);
  });

  test('a pool that cannot open leaves the other one syncing', () async {
    final remote = MemRemote();
    remote.files['sickdays-sync/devices/pc/sick_days.json'] = pythonSickLog;
    await refreshDayPools(
      openFree: () async => throw const FormatException('corrupt'),
      openSick: () =>
          SickDayPool.open(persistence: MemPersistence(), deviceId: 'phone'),
      sickSync: SickDaySync(
        openClient: () async => remote,
        scheduler: scheduler,
      ),
    );
    expect(caches['setSickDays'], ['2026-10-20']);
    expect(caches.containsKey('setFreeDays'), isFalse);
  });

  test('done is sent even when the refresh fails', () async {
    await expectLater(
      runHeadlessPoolSync(refresh: () async => throw StateError('boom')),
      throwsStateError,
    );
    expect(done, ['done']);
  });

  test('a missing done channel is swallowed', () async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(poolChannel, (call) async {
          throw PlatformException(code: 'gone');
        });
    await runHeadlessPoolSync(refresh: () async {});
  });
}
