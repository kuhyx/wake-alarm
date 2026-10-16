import 'dart:convert';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wake_alarm_sync/services/sick_day_keep.dart';
import 'package:wake_alarm_sync/services/sick_day_pool.dart';

import '../fake_day_pool_store.dart';

/// The per-locker keep set (sickdays 0.2.0, README "keep (0.2.0)").
final _today = DateTime(2026, 10, 16);
final _day = DateTime(2026, 10, 20);
bool _never(DateTime _) => false;

void main() {
  late MemPersistence disk;
  late SickDayPool pool;

  setUp(() async {
    disk = MemPersistence();
    pool = await SickDayPool.open(persistence: disk, deviceId: 'phone-uuid');
  });

  Map<String, Object?> wireFields(String iso) {
    final json = jsonDecode(disk.text!) as Map<String, Object?>;
    final record = json[iso]! as Map<String, Object?>;
    return record['fields']! as Map<String, Object?>;
  }

  Hlc hlcOf(String iso, String field) =>
      pool.snapshot()[iso]!.fields[field]!.$2;

  test('mark defaults to keep nothing: every locker stands down', () async {
    await pool.add(_day, isFree: _never, now: _today);
    final fields = wireFields('2026-10-20');
    expect((fields['keep']! as List).first, isEmpty);
    expect(
      {for (final f in fields.values) (f! as List).last},
      hasLength(1),
      reason: 'state, actor and keep share one tick',
    );
    for (final locker in SickLocker.all) {
      expect(pool.standsDown(locker, _day), isTrue, reason: locker);
    }
    expect(pool.keptLockers(_day), isEmpty);
  });

  test('a kept locker behaves normally; the rest stand down', () async {
    await pool.add(
      _day,
      isFree: _never,
      now: _today,
      keep: [SickLocker.workout, SickLocker.leetcode, SickLocker.workout],
    );
    expect((wireFields('2026-10-20')['keep']! as List).first, [
      'leetcode',
      'workout',
    ], reason: 'sorted and de-duplicated on the wire');
    expect(pool.standsDown(SickLocker.workout, _day), isFalse);
    expect(pool.standsDown(SickLocker.leetcode, _day), isFalse);
    expect(pool.standsDown(SickLocker.alarm, _day), isTrue);
    expect(pool.keptLockers(_day), {'leetcode', 'workout'});
  });

  test('a normal day stands nothing down and keeps nothing', () {
    expect(pool.standsDown(SickLocker.alarm, _day), isFalse);
    expect(pool.keptLockers(_day), isEmpty);
  });

  test('an unknown locker id is a programmer error', () async {
    expect(() => pool.standsDown('gym', _day), throwsArgumentError);
    await expectLater(
      pool.add(_day, isFree: _never, now: _today, keep: ['gym']),
      throwsArgumentError,
    );
    expect(pool.isSick(_day), isFalse, reason: 'nothing written');
  });

  test(
    'clear writes keep [] in the same tick; a re-add keeps nothing',
    () async {
      await pool.add(_day, isFree: _never, now: _today, keep: ['alarm']);
      await pool.remove(_day, now: _today);
      final fields = wireFields('2026-10-20');
      expect((fields['keep']! as List).first, isEmpty);
      expect({for (final f in fields.values) (f! as List).last}, hasLength(1));

      await pool.add(_day, isFree: _never, now: _today);
      expect(pool.standsDown(SickLocker.alarm, _day), isTrue);
    },
  );

  test('a keep-only edit stamps keep and actor, never state', () async {
    await pool.add(_day, isFree: _never, now: _today);
    final stateBefore = hlcOf('2026-10-20', 'state');

    await pool.setKept(_day, [SickLocker.alarm], now: _today);

    expect(hlcOf('2026-10-20', 'state'), stateBefore);
    expect(hlcOf('2026-10-20', 'keep'), hlcOf('2026-10-20', 'actor'));
    expect(hlcOf('2026-10-20', 'keep') > stateBefore, isTrue);
    expect(pool.standsDown(SickLocker.alarm, _day), isFalse);
    expect(pool.standsDown(SickLocker.diet, _day), isTrue);
  });

  test('a keep edit ticks after a PC state stamped in the future', () async {
    final future = Hlc(
      wallTimeMs: DateTime.now().toUtc().millisecondsSinceEpoch + 3600000,
      counter: 7,
      nodeId: 'pc',
    );
    await pool.replaceAll({
      '2026-10-20': Record(
        id: '2026-10-20',
        fields: {'state': ('sick', future), 'actor': ('pc', future)},
      ),
    });
    await pool.setKept(_day, [SickLocker.book], now: _today);
    expect(hlcOf('2026-10-20', 'keep') > future, isTrue);
    expect(pool.keptLockers(_day), {'book'}, reason: 'not stale');
  });

  test('a keep edit never re-asserts sick over a concurrent clear', () async {
    await pool.add(_day, isFree: _never, now: _today);
    final base = pool.snapshot();
    final other = await SickDayPool.open(
      persistence: MemPersistence(),
      deviceId: 'pc-uuid',
    );
    await other.replaceAll(base);
    await other.remove(_day, now: _today);
    await pool.setKept(_day, [SickLocker.alarm], now: _today);

    await pool.replaceAll(mergeLogs(pool.snapshot(), other.snapshot()));
    expect(pool.isSick(_day), isFalse);
    expect(pool.standsDown(SickLocker.workout, _day), isFalse);
  });

  test('setKept refuses a past day, a normal day and unknown ids', () async {
    await expectLater(
      pool.setKept(DateTime(2026, 10, 15), const [], now: _today),
      throwsA(
        isA<SickDayPolicyError>().having(
          (e) => e.message,
          'message',
          contains('2026-10-15 has already passed'),
        ),
      ),
    );
    await expectLater(
      pool.setKept(_day, const [], now: _today),
      throwsA(
        isA<SickDayPolicyError>().having(
          (e) => e.message,
          'message',
          '2026-10-20 is not a sick day.',
        ),
      ),
    );
    await pool.add(_day, isFree: _never, now: _today);
    await expectLater(
      pool.setKept(_day, const ['gym'], now: _today),
      throwsArgumentError,
    );
  });

  group('read rules, in order', () {
    const state = Hlc(wallTimeMs: 1000, counter: 0, nodeId: 'pc');
    const older = Hlc(wallTimeMs: 999, counter: 0, nodeId: 'pc');

    Future<Set<String>> keptWith(Field? keep) async {
      await pool.replaceAll({
        '2026-10-20': Record(
          id: '2026-10-20',
          fields: {'state': ('sick', state), 'keep': ?keep},
        ),
      });
      return pool.keptLockers(_day);
    }

    test('no keep field (0.1.0) keeps nothing', () async {
      expect(await keptWith(null), isEmpty);
    });

    test('a keep older than state is stale: keeps nothing', () async {
      expect(await keptWith((<Object?>['alarm'], older)), isEmpty);
    });

    test('an equal tick is not stale', () async {
      expect(await keptWith((<Object?>['alarm'], state)), {'alarm'});
    });

    test('a malformed keep keeps every locker (locks apply)', () async {
      expect(await keptWith(('alarm', state)), SickLocker.all.toSet());
      expect(await keptWith((<Object?>['alarm', 3], state)), hasLength(5));
      expect(pool.standsDown(SickLocker.alarm, _day), isFalse);
    });

    test('a stale malformed keep is just stale', () async {
      expect(await keptWith(('alarm', older)), isEmpty);
    });

    test('unknown ids in a valid list are ignored', () async {
      expect(await keptWith((<Object?>['gym', 'diet'], state)), {'diet'});
    });
  });

  test('reads a keep log the Python package wrote', () async {
    await pool.replaceAll(logFromJson(pythonKeepLog));
    expect(pool.keptLockers(_day), {'leetcode', 'workout'});
    expect(pool.keptLockers(DateTime(2026, 10, 22)), {'alarm'});
    expect(pool.keptLockers(DateTime(2026, 10, 23)), isEmpty);
    expect(pool.standDownIsoDates(SickLocker.alarm), [
      '2026-10-20',
      '2026-10-23',
    ]);
  });

  test('a 0.1.0 Python log keeps nothing on its sick day', () async {
    await pool.replaceAll(logFromJson(pythonSickLog));
    expect(pool.standDownIsoDates(SickLocker.alarm), ['2026-10-20']);
  });

  test('stand-down dates keep past days, drop kept ones', () async {
    final past = DateTime(2026, 10, 10);
    final hlc = Hlc.newTick('pc');
    await pool.replaceAll({
      '2026-10-10': Record(
        id: '2026-10-10',
        fields: {'state': ('sick', hlc), 'keep': (<Object?>[], hlc)},
      ),
      '2026-10-11': Record(
        id: '2026-10-11',
        fields: {
          'state': ('sick', hlc),
          'keep': (<Object?>['alarm'], hlc),
        },
      ),
    });
    expect(pool.standsDown(SickLocker.alarm, past), isTrue);
    expect(pool.standDownIsoDates(SickLocker.alarm), ['2026-10-10']);
    expect(pool.sickIsoDates(), ['2026-10-10', '2026-10-11']);
  });
}
