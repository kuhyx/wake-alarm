import 'dart:convert';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wake_alarm_sync/services/sick_day_pool.dart';

import '../fake_day_pool_store.dart';

final _today = DateTime(2026, 10, 16);
bool _never(DateTime _) => false;

void main() {
  late MemPersistence disk;
  late SickDayPool pool;

  setUp(() async {
    disk = MemPersistence();
    pool = await SickDayPool.open(persistence: disk, deviceId: 'phone-uuid');
  });

  test('every day is normal until marked', () {
    expect(pool.isSick(_today), isFalse);
    expect(pool.sickDays(), isEmpty);
  });

  test('marks today and a future day, ascending, in the wire format', () async {
    await pool.add(DateTime(2026, 10, 20), isFree: _never, now: _today);
    await pool.add(_today, isFree: _never, now: _today);

    expect(pool.isSick(DateTime(2026, 10, 20, 14)), isTrue);
    expect(pool.sickIsoDates(), ['2026-10-16', '2026-10-20']);
    final json = jsonDecode(disk.text!) as Map<String, Object?>;
    final record = json['2026-10-20']! as Map<String, Object?>;
    final fields = record['fields']! as Map<String, Object?>;
    final state = fields['state']! as List<Object?>;
    final actor = fields['actor']! as List<Object?>;
    expect(state.first, 'sick');
    expect(actor.first, 'phone-uuid');
    expect(state.last, actor.last, reason: 'one HLC tick per write');
    expect(record['deleted'], isFalse);
  });

  test('clearing flips state to cleared and never tombstones', () async {
    await pool.add(DateTime(2026, 10, 20), isFree: _never, now: _today);
    await pool.remove(DateTime(2026, 10, 20), now: _today);

    expect(pool.isSick(DateTime(2026, 10, 20)), isFalse);
    final record = pool.snapshot()['2026-10-20']!;
    expect(record.deleted, isFalse);
    expect(record.fields['state']!.$1, 'cleared');

    // ...so it can be marked again.
    await pool.add(DateTime(2026, 10, 20), isFree: _never, now: _today);
    expect(pool.isSick(DateTime(2026, 10, 20)), isTrue);
  });

  test('refuses a past day for both add and remove', () async {
    final yesterday = DateTime(2026, 10, 15);
    await expectLater(
      pool.add(yesterday, isFree: _never, now: _today),
      throwsA(
        isA<SickDayPolicyError>().having(
          (e) => e.message,
          'message',
          contains('2026-10-15 has already passed'),
        ),
      ),
    );
    await expectLater(
      pool.remove(yesterday, now: _today),
      throwsA(isA<SickDayPolicyError>()),
    );
  });

  test('refuses an already-sick day and clearing a normal day', () async {
    await pool.add(DateTime(2026, 10, 20), isFree: _never, now: _today);
    await expectLater(
      pool.add(DateTime(2026, 10, 20), isFree: _never, now: _today),
      throwsA(
        isA<SickDayPolicyError>().having(
          (e) => e.toString(),
          'toString',
          '2026-10-20 is already a sick day.',
        ),
      ),
    );
    await expectLater(
      pool.remove(DateTime(2026, 10, 22), now: _today),
      throwsA(
        isA<SickDayPolicyError>().having(
          (e) => e.message,
          'message',
          '2026-10-22 is not a sick day.',
        ),
      ),
    );
  });

  test('refuses a free day and names the free-day pool', () async {
    await expectLater(
      pool.add(
        DateTime(2026, 10, 20),
        isFree: (day) => day == DateTime(2026, 10, 20),
        now: _today,
      ),
      throwsA(
        isA<SickDayPolicyError>().having(
          (e) => e.message,
          'message',
          '2026-10-20 is a free day — release it in Free days first.',
        ),
      ),
    );
    expect(pool.isSick(DateTime(2026, 10, 20)), isFalse);
  });

  test('reads a log the Python package wrote', () async {
    await pool.replaceAll(logFromJson(pythonSickLog));
    expect(pool.isSick(DateTime(2026, 10, 20)), isTrue);
    expect(pool.isSick(DateTime(2026, 10, 21)), isFalse, reason: 'cleared');
    expect(pool.sickIsoDates(), ['2026-10-20']);
  });

  test('a tombstone, an unknown state or a junk id is not sick', () async {
    final hlc = Hlc.newTick('pc');
    await pool.replaceAll({
      '2026-10-20': Record(
        id: '2026-10-20',
        fields: {'state': ('sick', hlc)},
        deleted: true,
        deletedHlc: hlc,
      ),
      '2026-10-22': Record(id: '2026-10-22', fields: {'state': ('ill', hlc)}),
      'nonsense': Record(id: 'nonsense', fields: {'state': ('sick', hlc)}),
    });
    expect(pool.isSick(DateTime(2026, 10, 20)), isFalse);
    expect(pool.isSick(DateTime(2026, 10, 22)), isFalse);
    expect(pool.sickIsoDates(), isEmpty);
  });

  test('persists across a reopen', () async {
    await pool.add(DateTime(2026, 10, 20), isFree: _never, now: _today);
    final again = await SickDayPool.open(persistence: disk, deviceId: 'x');
    expect(again.isSick(DateTime(2026, 10, 20)), isTrue);
  });
}
