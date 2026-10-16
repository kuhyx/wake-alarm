import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wake_alarm_sync/services/alarm_scheduler.dart';
import 'package:wake_alarm_sync/services/sick_day_pool.dart';
import 'package:wake_alarm_sync/services/sick_day_sync.dart';

import '../fake_day_pool_store.dart';

final _today = DateTime(2026, 10, 16);
bool _never(DateTime _) => false;

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late List<MethodCall> calls;
  late AlarmScheduler scheduler;
  var channelThrows = false;

  setUp(() {
    calls = <MethodCall>[];
    channelThrows = false;
    const channel = MethodChannel(AlarmScheduler.channelName);
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
          calls.add(call);
          if (channelThrows) throw PlatformException(code: 'no_platform');
          return null;
        });
    scheduler = AlarmScheduler(channel: channel);
  });

  Future<SickDayPool> openPool() =>
      SickDayPool.open(persistence: MemPersistence(), deviceId: 'phone');

  List<String> lastCache() {
    expect(calls.last.method, 'setSickDays');
    return ((calls.last.arguments as Map)['dates'] as List).cast<String>();
  }

  test("pulls the PC's sick day and pushes the phone's own", () async {
    final remote = MemRemote();
    remote.files['${SickDayPool.pathPrefix}/$pythonDeviceId/'
            '${SickDayPool.filename}'] =
        pythonSickLog;
    final pool = await openPool();
    await pool.add(DateTime(2026, 10, 23), isFree: _never, now: _today);

    final sync = SickDaySync(
      openClient: () async => remote,
      scheduler: scheduler,
    );
    expect(await sync.sync(pool), 'Synced ✓');

    expect(pool.isSick(DateTime(2026, 10, 20)), isTrue, reason: 'pulled');
    expect(pool.isSick(DateTime(2026, 10, 21)), isFalse, reason: 'cleared');
    final pushed = remote.files['sickdays-sync/devices/phone/sick_days.json'];
    expect(pushed, contains('"2026-10-23"'));
    expect(lastCache(), ['2026-10-20', '2026-10-23']);
  });

  test('a later clear on the phone beats an earlier PC mark', () async {
    final remote = MemRemote();
    remote.files['${SickDayPool.pathPrefix}/$pythonDeviceId/'
            '${SickDayPool.filename}'] =
        pythonSickLog;
    final pool = await openPool();
    final sync = SickDaySync(
      openClient: () async => remote,
      scheduler: scheduler,
    );
    await sync.sync(pool);
    await pool.remove(DateTime(2026, 10, 20), now: _today);
    await sync.sync(pool);
    expect(pool.isSick(DateTime(2026, 10, 20)), isFalse);
    expect(lastCache(), isEmpty);
  });

  test('only days on which the alarm stands down reach the cache', () async {
    final pool = await openPool();
    await pool.add(_today, isFree: _never, now: _today, keep: ['alarm']);
    await pool.add(
      DateTime(2026, 10, 20),
      isFree: _never,
      now: _today,
      keep: ['leetcode'],
    );
    final sync = SickDaySync(
      openClient: () async => null,
      scheduler: scheduler,
    );
    await sync.sync(pool);
    expect(lastCache(), ['2026-10-20'], reason: 'kept alarm rings');

    await pool.setKept(DateTime(2026, 10, 20), ['alarm'], now: _today);
    await sync.sync(pool);
    expect(lastCache(), isEmpty, reason: 'a keep-only edit reaches it too');
  });

  test('not connected to Firebase still refreshes the cache', () async {
    final pool = await openPool();
    await pool.add(_today, isFree: _never, now: _today);
    final sync = SickDaySync(
      openClient: () async => null,
      scheduler: scheduler,
    );
    expect(await sync.sync(pool), contains('connect Firebase'));
    expect(lastCache(), ['2026-10-16']);
  });

  test('an unreachable remote reports an error and keeps the cache', () async {
    final pool = await openPool();
    await pool.add(_today, isFree: _never, now: _today);
    final sync = SickDaySync(
      openClient: () async => BrokenRemote(),
      scheduler: scheduler,
    );
    expect(await sync.sync(pool), startsWith('Error:'));
    expect(lastCache(), ['2026-10-16']);
  });

  test('a client factory that throws is reported, not propagated', () async {
    final pool = await openPool();
    final sync = SickDaySync(
      openClient: () async => throw StateError('keystore locked'),
      scheduler: scheduler,
    );
    expect(await sync.sync(pool), contains('keystore locked'));
    expect(lastCache(), isEmpty);
  });

  test('a missing platform channel does not fail the sync', () async {
    channelThrows = true;
    final sync = SickDaySync(
      openClient: () async => MemRemote(),
      scheduler: scheduler,
    );
    expect(await sync.sync(await openPool()), 'Synced ✓');
  });
}
