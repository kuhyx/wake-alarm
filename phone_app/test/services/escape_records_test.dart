import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:wake_alarm_sync/services/escape_hatch.dart';
import 'package:wake_alarm_sync/services/escape_log.dart';
import 'package:wake_alarm_sync/services/iso_time.dart';
import 'package:wake_alarm_sync/services/ring_started_store.dart';
import 'package:wake_alarm_sync/services/stakes.dart';

import '../fake_enforcement_channel.dart';

final String _reason = 'x' * escapeReasonMinChars;

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  group('isoWithOffset / escapeHatchOpen', () {
    test('carries the local offset and round-trips to the same instant', () {
      final when = DateTime(2026, 10, 1, 7, 2, 9);
      final iso = isoWithOffset(when);
      expect(iso, matches(RegExp(r'^2026-10-01T07:02:09[+-]\d\d:\d\d$')));
      expect(DateTime.parse(iso).isAtSameMomentAs(when), isTrue);
      expect(isoDate(DateTime(987, 3, 4)), '0987-03-04');
    });

    test('the hatch is open through its last day, inclusive', () {
      expect(escapeHatchOpen(DateTime(2026, 10, 15, 23, 59)), isTrue);
      expect(escapeHatchOpen(DateTime(2026, 10, 16)), isFalse);
    });
  });

  group('EscapeLog', () {
    test('adds newest first, with the contract fields', () async {
      final first = await EscapeLog.add('first', now: DateTime(2026, 10, 1, 7));
      await EscapeLog.add('second', now: DateTime(2026, 10, 2, 7));
      final entries = await EscapeLog.load();
      expect(entries.map((e) => e['reason']), ['second', 'first']);
      expect(first.keys, containsAll(<String>['id', 'date', 'at', 'reason']));
      expect(first['date'], '2026-10-01');
      expect(first['id'], isNot(entries.first['id']));
    });

    test('keeps at most 30', () async {
      for (var i = 0; i < EscapeLog.carried + 3; i++) {
        await EscapeLog.add('r$i', now: DateTime(2026, 10, 1, 7, i));
      }
      final entries = await EscapeLog.load();
      expect(entries, hasLength(EscapeLog.carried));
      expect(entries.first['reason'], 'r${EscapeLog.carried + 2}');
    });

    test('malformed storage reads as no escapes', () async {
      SharedPreferences.setMockInitialValues({EscapeLog.key: 'not json'});
      expect(await EscapeLog.load(), isEmpty);
      SharedPreferences.setMockInitialValues({EscapeLog.key: '{"a": 1}'});
      expect(await EscapeLog.load(), isEmpty);
    });
  });

  group('RingStartedStore', () {
    test('the first open of the day wins; a new day replaces it', () async {
      final first = await RingStartedStore.recordFirst(
        DateTime(2026, 10, 1, 7),
      );
      final again = await RingStartedStore.recordFirst(
        DateTime(2026, 10, 1, 7, 30),
      );
      expect(again, first);
      expect(first['at'], isoWithOffset(DateTime(2026, 10, 1, 7)));
      final next = await RingStartedStore.recordFirst(DateTime(2026, 10, 2, 7));
      expect(next['date'], '2026-10-02');
      expect(await RingStartedStore.load(), next);
    });

    test('malformed storage reads as none', () async {
      SharedPreferences.setMockInitialValues({RingStartedStore.key: '[1'});
      expect(await RingStartedStore.load(), isNull);
      SharedPreferences.setMockInitialValues({RingStartedStore.key: '[1]'});
      expect(await RingStartedStore.load(), isNull);
    });
  });

  group('EscapeHatch', () {
    late FakeEnforcementChannel native;
    setUp(() => native = FakeEnforcementChannel()..install());

    EscapeHatch hatch(DateTime now) => EscapeHatch(now: () => now);

    test('a long enough reason escapes natively, then logs it', () async {
      final ok = await hatch(DateTime(2026, 10, 1, 7)).use('  $_reason  ');
      expect(ok, isTrue);
      expect(native.methods, ['escapeToday']);
      final entry = (await EscapeLog.load()).single;
      expect(entry['reason'], _reason);
      expect(entry['date'], '2026-10-01');
    });

    test('a short reason is refused before anything happens', () async {
      final short = 'x' * (escapeReasonMinChars - 1);
      expect(await hatch(DateTime(2026, 10)).use(short), isFalse);
      expect(native.calls, isEmpty);
    });

    test('after the last day it is closed', () async {
      final closed = hatch(DateTime(2026, 10, 16));
      expect(closed.isOpen, isFalse);
      expect(await closed.use(_reason), isFalse);
      expect(native.calls, isEmpty);
    });

    test('a native refusal records nothing', () async {
      native.escapeResult = false;
      expect(await hatch(DateTime(2026, 10)).use(_reason), isFalse);
      expect(await EscapeLog.load(), isEmpty);
    });
  });
}
