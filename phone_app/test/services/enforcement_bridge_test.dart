import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wake_alarm_sync/services/alarm_scheduler.dart';
import 'package:wake_alarm_sync/services/enforcement_bridge.dart';
import 'package:wake_alarm_sync/services/enforcement_state.dart';

import '../fake_enforcement_channel.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late FakeEnforcementChannel native;
  final bridge = EnforcementBridge();

  setUp(() {
    native = FakeEnforcementChannel()..install();
  });

  test('appendEvent passes kind and data; readEvents decodes them', () async {
    await bridge.appendEvent('ring_screen_opened');
    await bridge.appendEvent('ring_started_published', {'date': '2026-10-01'});
    expect(native.calls.first.arguments, <String, Object?>{
      'kind': 'ring_screen_opened',
      'data': <String, Object?>{},
    });
    final events = await bridge.readEvents();
    expect(events.map((e) => e['kind']), [
      'ring_started_published',
      'ring_screen_opened',
    ]);
    expect(events.first['data'], {'date': '2026-10-01'});
  });

  Future<void> answerReadEvents(Object? reply) async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
          const MethodChannel(AlarmScheduler.channelName),
          (call) async => reply,
        );
  }

  test(
    'readEvents tolerates no answer, a non-list and stray entries',
    () async {
      await answerReadEvents(null);
      expect(await bridge.readEvents(), isEmpty);
      await answerReadEvents('{"not": "a list"}');
      expect(await bridge.readEvents(), isEmpty);
      await answerReadEvents('[1, {"kind": "boot"}]');
      expect(await bridge.readEvents(), [
        {'kind': 'boot'},
      ]);
    },
  );

  test('state parses the native map; no answer is null', () async {
    expect(await bridge.state(), isNull);
    native.state = nativeState(streak: 2, lockedThrough: '2026-10-03');
    final state = await bridge.state();
    expect(state?.streak, 2);
    expect(state?.lockedThrough, DateTime(2026, 10, 3));
  });

  test('escapeToday returns the native answer, false when silent', () async {
    expect(await bridge.escapeToday(), isTrue);
    native.escapeResult = false;
    expect(await bridge.escapeToday(), isFalse);
    await answerReadEvents(null);
    expect(await bridge.escapeToday(), isFalse);
  });

  group('EnforcementState.fromMap', () {
    test('null, or a map without a date, is null', () {
      expect(EnforcementState.fromMap(null), isNull);
      expect(EnforcementState.fromMap({'streak': 1}), isNull);
      expect(EnforcementState.fromMap({'today': 'garbage'}), isNull);
    });

    test('reads every field; missing ones take safe defaults', () {
      final full = EnforcementState.fromMap(
        nativeState(
          dismissedToday: true,
          escapedToday: true,
          freeToday: true,
          freeTomorrow: true,
          streak: 3,
          lockedThrough: '2026-10-04',
          lastMiss: '2026-10-01',
          updatedAt: '2026-10-01T07:15:05+02:00',
        ),
      )!;
      expect(full.today, DateTime(2026, 10));
      expect((full.alarmHour, full.alarmMinute), (7, 0));
      expect(full.dismissedToday && full.escapedToday, isTrue);
      expect(full.freeToday && full.freeTomorrow, isTrue);
      expect(full.lastMiss, DateTime(2026, 10));
      expect(full.updatedAt, '2026-10-01T07:15:05+02:00');
      expect(full.lockIfMissToday, DateTime(2026, 10, 2));
      expect(full.lockIfMissTomorrow, DateTime(2026, 10, 3));

      final bare = EnforcementState.fromMap({'today': '2026-10-01'})!;
      expect(bare.streak, 0);
      expect(bare.alarmHour, isNull);
      expect(bare.dismissedToday, isFalse);
      expect(bare.lockedThrough, isNull);
    });

    test('toStickStateJson is the contract shape', () {
      final state = EnforcementState.fromMap(
        nativeState(
          streak: 1,
          lockedThrough: '2026-10-02',
          lastMiss: '2026-10-01',
        ),
      )!;
      expect(state.toStickStateJson(), {
        'streak': 1,
        'locked_through': '2026-10-02',
        'last_miss': '2026-10-01',
      });
      final clean = EnforcementState.fromMap(nativeState())!;
      expect(clean.toStickStateJson(), {
        'streak': 0,
        'locked_through': null,
        'last_miss': null,
      });
    });
  });
}
