import 'dart:convert';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:wake_alarm_sync/services/alarm_sync_service.dart';
import 'package:wake_alarm_sync/services/data_export.dart';
import 'package:wake_alarm_sync/services/free_day_pool.dart';
import 'package:wake_alarm_sync/services/ramp_progress.dart';
import 'package:wake_alarm_sync/services/sick_day_pool.dart';

import '../fake_day_pool_store.dart';

final _now = DateTime(2026, 11, 2);

/// One install's three stores, on in-memory persistence.
class _Device {
  _Device._(this.alarm, this.free, this.sick);

  final AlarmSyncService alarm;
  final FreeDayPool free;
  final SickDayPool sick;

  static Future<_Device> open(String id) async => _Device._(
    await AlarmSyncService.open(persistence: MemPersistence(), deviceId: id),
    await FreeDayPool.open(persistence: MemPersistence(), deviceId: id),
    await SickDayPool.open(persistence: MemPersistence(), deviceId: id),
  );

  Map<String, LogSlot> get slots => {
    'alarm': (snapshot: alarm.snapshot, replaceAll: alarm.replaceAll),
    'free_days': (snapshot: free.snapshot, replaceAll: free.replaceAll),
    'sick_days': (snapshot: sick.snapshot, replaceAll: sick.replaceAll),
  };

  /// Every log as plain JSON, so equality is structural.
  Map<String, Object?> get state => {
    for (final e in slots.entries)
      e.key: jsonDecode(logToJson(e.value.snapshot())),
  };
}

Future<_Device> _populated() async {
  final device = await _Device.open('phone-a');
  await device.alarm.setLocal(7, 42);
  await device.free.mark(DateTime(2026, 11, 3), reason: 'trip', now: _now);
  await device.sick.add(
    DateTime(2026, 11, 5),
    isFree: device.free.isFree,
    now: _now,
  );
  return device;
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  test(
    'export -> import into an empty store reproduces every record',
    () async {
      await RampProgress.merge(['2026-10-25', '2026-10-26']);
      final source = await _populated();
      final file = await buildExport(source.slots, now: _now);

      final decoded = jsonDecode(file) as Map<String, dynamic>;
      expect(decoded['format'], 'wake_alarm_export');
      expect(decoded['version'], 1);

      SharedPreferences.setMockInitialValues(<String, Object>{});
      final target = await _Device.open('phone-b');
      await importExport(file, target.slots);

      expect(target.state, equals(source.state));
      expect(await RampProgress.load(), {'2026-10-25', '2026-10-26'});
    },
  );

  test('importing the same file twice equals importing it once', () async {
    final file = await buildExport((await _populated()).slots, now: _now);
    final target = await _Device.open('phone-b');

    await importExport(file, target.slots);
    final once = target.state;
    await importExport(file, target.slots);

    expect(target.state, equals(once));
  });

  test('import into a non-empty store keeps the existing records', () async {
    final file = await buildExport((await _populated()).slots, now: _now);
    await RampProgress.merge(['2026-10-18']);
    final target = await _Device.open('phone-b');
    await target.free.mark(DateTime(2026, 11, 9), now: _now);
    final before = target.state;

    await importExport(file, target.slots);

    expect(target.free.isFree(DateTime(2026, 11, 9)), isTrue);
    expect(target.free.isFree(DateTime(2026, 11, 3)), isTrue);
    expect(target.sick.isSick(DateTime(2026, 11, 5)), isTrue);
    expect(target.alarm.currentAlarm, (hour: 7, minute: 42));
    final freeBefore = (before['free_days']! as Map)['2026-11-09'];
    expect((target.state['free_days']! as Map)['2026-11-09'], freeBefore);
    expect(await RampProgress.load(), contains('2026-10-18'));
  });

  test('a file that is not a wake_alarm export changes nothing', () async {
    final target = await _populated();
    final before = target.state;

    for (final bad in [
      'not json',
      '[]',
      '{"days": []}',
      '{"format": "wake_alarm_export", "version": 1, "logs": {"alarm": 3}}',
    ]) {
      await expectLater(importExport(bad, target.slots), throwsFormatException);
    }
    expect(target.state, equals(before));
  });
}
