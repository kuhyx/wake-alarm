import 'dart:convert';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wake_alarm_sync/services/free_day_pool.dart';

class _MemPersistence implements LogPersistence {
  String? text;

  @override
  Future<String?> read() async => text;

  @override
  Future<void> write(String value) async => text = value;
}

final _today = DateTime(2026, 9, 11);
final _tomorrow = DateTime(2026, 9, 12);
final _yesterday = DateTime(2026, 9, 10);

Future<FreeDayPool> _open([_MemPersistence? persistence]) => FreeDayPool.open(
  persistence: persistence ?? _MemPersistence(),
  deviceId: 'phone-test',
);

void main() {
  group('dates', () {
    test('toIso pads and parseIso round-trips', () {
      expect(FreeDayPool.toIso(DateTime(2026, 1, 5)), '2026-01-05');
      expect(FreeDayPool.parseIso('2026-01-05'), DateTime(2026, 1, 5));
    });

    test('parseIso rejects junk and impossible dates', () {
      expect(FreeDayPool.parseIso('alarm'), isNull);
      expect(FreeDayPool.parseIso('2026-02-30'), isNull);
      expect(FreeDayPool.parseIso('2026-9-1'), isNull);
    });

    test('dateOnly drops the time of day and today() is local', () {
      expect(
        FreeDayPool.dateOnly(DateTime(2026, 9, 11, 23, 59)),
        DateTime(2026, 9, 11),
      );
      expect(FreeDayPool.today().hour, 0);
    });
  });

  group('mark', () {
    test('a future day becomes free and is not consumed', () async {
      final pool = await _open();
      await pool.mark(_tomorrow, reason: 'travelling', now: _today);
      expect(pool.isFree(_tomorrow), isTrue);
      expect(pool.reasonFor(_tomorrow), 'travelling');
      expect(pool.freeIsoDates(), ['2026-09-12']);
      expect(pool.spent(2026), 1);
      expect(pool.remaining(2026), FreeDayPool.annualBudget - 1);
    });

    test('today is allowed and immediately consumed', () async {
      final pool = await _open();
      await pool.mark(_today, now: _today);
      expect(pool.isFree(_today), isTrue);
      await pool.release(_today, now: _today);
      expect(pool.isFree(_today), isFalse);
      // Those hours were already unguarded: no refund.
      expect(pool.spent(2026), 1);
    });

    test('the time of day on the picked date is ignored', () async {
      final pool = await _open();
      await pool.mark(DateTime(2026, 9, 12, 15, 30), now: _today);
      expect(pool.isFree(_tomorrow), isTrue);
    });

    test('a past day is refused', () async {
      final pool = await _open();
      await expectLater(
        pool.mark(_yesterday, now: _today),
        throwsA(
          isA<FreeDayPolicyError>().having(
            (e) => e.toString(),
            'message',
            contains('already passed'),
          ),
        ),
      );
      expect(pool.freeDays(), isEmpty);
    });

    test('an already-free day is refused', () async {
      final pool = await _open();
      await pool.mark(_tomorrow, now: _today);
      await expectLater(
        pool.mark(_tomorrow, now: _today),
        throwsA(isA<FreeDayPolicyError>()),
      );
    });

    test('the budget is per calendar year and refuses the 36th', () async {
      final pool = await _open();
      for (var i = 0; i < FreeDayPool.annualBudget; i++) {
        await pool.mark(DateTime(2026, 10, 1 + i), now: _today);
      }
      expect(pool.remaining(2026), 0);
      await expectLater(
        pool.mark(DateTime(2026, 12, 24), now: _today),
        throwsA(isA<FreeDayPolicyError>()),
      );
      // Next year is a fresh pool.
      await pool.mark(DateTime(2027, 1, 2), now: _today);
      expect(pool.remaining(2027), FreeDayPool.annualBudget - 1);
    });
  });

  group('release', () {
    test('a future day is refunded', () async {
      final pool = await _open();
      await pool.mark(_tomorrow, now: _today);
      await pool.release(_tomorrow, now: _today);
      expect(pool.isFree(_tomorrow), isFalse);
      expect(pool.spent(2026), 0);
      // And can be marked again: a flip, not a tombstone.
      await pool.mark(_tomorrow, now: _today);
      expect(pool.isFree(_tomorrow), isTrue);
    });

    test('a day that is not free is refused', () async {
      final pool = await _open();
      await expectLater(
        pool.release(_tomorrow, now: _today),
        throwsA(isA<FreeDayPolicyError>()),
      );
    });

    test('consumed is sticky across a release and re-mark', () async {
      final pool = await _open();
      await pool.mark(_tomorrow, now: _today);
      // The day arrives, then is released after the fact.
      await pool.release(_tomorrow, now: _tomorrow);
      expect(pool.spent(2026), 1);
      // Re-marking a later day does not resurrect the refund either.
      await pool.mark(DateTime(2026, 9, 20), now: _tomorrow);
      expect(pool.spent(2026), 2);
    });
  });

  group('storage', () {
    test("records use the Python package's exact shape", () async {
      final persistence = _MemPersistence();
      final pool = await _open(persistence);
      await pool.mark(_tomorrow, reason: 'r', now: _today);
      final json = jsonDecode(persistence.text!) as Map<String, dynamic>;
      final record = json['2026-09-12'] as Map<String, dynamic>;
      final fields = record['fields'] as Map<String, dynamic>;
      expect(
        fields.keys,
        containsAll(['state', 'consumed', 'actor', 'reason']),
      );
      expect((fields['state'] as List).first, 'free');
      expect((fields['consumed'] as List).first, false);
      expect((fields['actor'] as List).first, 'phone-test');
      expect(record['deleted'], false);
      // Every field shares one clock tick.
      final ticks = fields.values.map((v) => (v as List)[1]).toSet();
      expect(ticks, hasLength(1));
    });

    test('a tombstoned or malformed record reads as not free', () async {
      final persistence = _MemPersistence();
      final hlc = Hlc.newTick('other').toStr();
      persistence.text = jsonEncode({
        '2026-09-12': {
          'id': '2026-09-12',
          'fields': {
            'state': ['free', hlc],
          },
          'deleted': true,
          'deleted_hlc': hlc,
        },
        '2026-09-13': {
          'id': '2026-09-13',
          'fields': {
            'state': [7, hlc],
          },
          'deleted': false,
          'deleted_hlc': null,
        },
        'not-a-date': {
          'id': 'not-a-date',
          'fields': {
            'state': ['free', hlc],
          },
          'deleted': false,
          'deleted_hlc': null,
        },
      });
      final pool = await _open(persistence);
      expect(pool.isFree(_tomorrow), isFalse);
      expect(pool.isFree(DateTime(2026, 9, 13)), isFalse);
      expect(pool.freeDays(), isEmpty);
      expect(pool.spent(2026), 0);
      expect(pool.reasonFor(_tomorrow), '');
    });

    test('remaining clamps at zero after a merge over budget', () async {
      final pool = await _open();
      final peer = <String, Record>{};
      final hlc = Hlc.newTick('peer');
      for (var i = 0; i < FreeDayPool.annualBudget + 3; i++) {
        final id = FreeDayPool.toIso(DateTime(2026, 1, 1 + i));
        peer[id] = Record(
          id: id,
          fields: {'state': ('free', hlc), 'consumed': (true, hlc)},
        );
      }
      await pool.replaceAll(peer);
      expect(pool.snapshot(), hasLength(FreeDayPool.annualBudget + 3));
      expect(pool.remaining(2026), 0);
    });
  });
}
