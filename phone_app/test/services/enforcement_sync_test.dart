import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:wake_alarm_sync/services/alarm_sync_service.dart';
import 'package:wake_alarm_sync/services/enforcement_sync.dart';
import 'package:wake_alarm_sync/services/escape_log.dart';
import 'package:wake_alarm_sync/services/iso_time.dart';
import 'package:wake_alarm_sync/services/ring_start_recorder.dart';
import 'package:wake_alarm_sync/services/ring_started_store.dart';
import 'package:wake_alarm_sync/services/settings_sync.dart';

import '../fake_enforcement_channel.dart';
import '../fake_secure_storage.dart';

class _MemPersistence implements LogPersistence {
  String? text;

  @override
  Future<String?> read() async => text;

  @override
  Future<void> write(String value) async => text = value;
}

Future<AlarmSyncService> _open() =>
    AlarmSyncService.open(persistence: _MemPersistence(), deviceId: 'me');

Map<String, Object?> _event(DateTime at, String kind) => <String, Object?>{
  'at': isoWithOffset(at),
  'kind': kind,
  'data': <String, Object?>{},
};

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  final now = DateTime(2026, 10, 1, 7, 20);
  late FakeEnforcementChannel native;

  setUp(() {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    installFakeSecureStorage();
    native = FakeEnforcementChannel()
      ..now = (() => now)
      ..install();
  });

  group('stageEnforcementData', () {
    test('nothing recorded anywhere stages nothing', () async {
      native.state = nativeState();
      final service = await _open();
      await stageEnforcementData(service, now: () => now);
      for (final field in [
        ringStartedField,
        escapesField,
        stickStateField,
        phoneEventsField,
      ]) {
        expect(service.field(field), isNull, reason: field);
      }
    });

    test('every field lands, stamped by its own newest entry', () async {
      final ring = await RingStartedStore.recordFirst(DateTime(2026, 10, 1, 7));
      await EscapeLog.add('a reason', now: DateTime(2026, 10, 1, 7, 10));
      native
        ..state = nativeState(
          streak: 1,
          lockedThrough: '2026-10-02',
          lastMiss: '2026-10-01',
          updatedAt: '2026-10-01T07:15:05+02:00',
        )
        ..events.add(_event(DateTime(2026, 10, 1, 7, 15), 'lockdown_sent'));
      final service = await _open();

      // The clock is pinned: on the real one the 2026-10-01 event aged past
      // boundEvents' 14-day window on 2026-10-16 and the test went red.
      await stageLocalSettings(service, now: () => now);

      expect(service.field(ringStartedField)?.$1, ring);
      final escapes = service.field(escapesField)!;
      expect((escapes.$1! as List).single, containsPair('reason', 'a reason'));
      expect(
        escapes.$2.wallTimeMs,
        DateTime(2026, 10, 1, 7, 10).millisecondsSinceEpoch,
      );
      expect(service.field(stickStateField)?.$1, {
        'streak': 1,
        'locked_through': '2026-10-02',
        'last_miss': '2026-10-01',
      });
      final events = service.field(phoneEventsField)!.$1! as List;
      expect(events.single, containsPair('kind', 'lockdown_sent'));
    });

    test('restaging an unchanged log pushes nothing new', () async {
      native.events.add(_event(DateTime(2026, 10, 1, 7), 'boot'));
      final service = await _open();
      await stageEnforcementData(service, now: () => now);
      final before = service.field(phoneEventsField)!.$2;
      await stageEnforcementData(service, now: () => now);
      expect(service.field(phoneEventsField)!.$2, before);
    });

    test('a stick never changed (no updatedAt) is not staged', () async {
      native.state = nativeState();
      final service = await _open();
      await stageEnforcementData(service, now: () => now);
      expect(service.field(stickStateField), isNull);
    });
  });

  test('no native side still stages the Dart-held records', () async {
    // Replaces the fake with no handler at all.
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(native.channel, null);
    await EscapeLog.add('offline', now: now);
    final service = await _open();
    await stageEnforcementData(service, now: () => now);
    expect(service.field(escapesField), isNotNull);
    expect(service.field(phoneEventsField), isNull);
  });

  group('boundEvents', () {
    test('newest first, at most 400, none older than 14 days', () {
      final events = [
        _event(now.subtract(const Duration(days: 15)), 'stale'),
        <String, Object?>{'at': 'garbage', 'kind': 'unplaced'},
        for (var i = 0; i < eventsCarried + 5; i++)
          _event(now.subtract(Duration(minutes: i)), 'e$i'),
      ]..shuffle();
      final bounded = boundEvents(events, now);
      expect(bounded, hasLength(eventsCarried));
      expect(bounded.first['kind'], 'e0');
      expect(bounded.map((e) => e['kind']), isNot(contains('stale')));
      expect(bounded.map((e) => e['kind']), isNot(contains('unplaced')));
    });
  });

  group('RingStartRecorder', () {
    test('unconfigured: logs the open and keeps the start locally', () async {
      final recorder = RingStartRecorder(now: () => now);
      expect(await recorder.record(), isFalse);
      expect(native.events.single['kind'], 'ring_screen_opened');
      expect((await RingStartedStore.load())?['date'], '2026-10-01');
    });

    test('configured: stages ring_started, pushes, logs it', () async {
      SharedPreferences.setMockInitialValues({'github_token': 'ghp_x'});
      final service = await _open();
      final pushed = <String>[];
      final recorder = RingStartRecorder(
        open: () async => service,
        push: (s, token) async => pushed.add(token),
        now: () => now,
      );
      expect(await recorder.record(), isTrue);
      expect(pushed, ['ghp_x']);
      expect(
        service.field(ringStartedField)?.$1,
        containsPair('at', isNotNull),
      );
      expect(native.events.first['kind'], 'ring_started_published');
      expect(native.events.first['data'], {
        'date': '2026-10-01',
        'source': 'ring_screen',
      });
    });

    test(
      'the headless source logs no open; a later screen skips the push',
      () async {
        SharedPreferences.setMockInitialValues({'github_token': 'ghp_x'});
        final service = await _open();
        final pushed = <String>[];
        Future<void> push(AlarmSyncService _, String token) async =>
            pushed.add(token);
        final headless = RingStartRecorder(
          open: () async => service,
          push: push,
          now: () => now,
          openedEvent: null,
          source: 'alarm',
        );
        expect(await headless.record(), isTrue);
        expect(native.events.single['kind'], 'ring_started_published');
        expect(native.events.single['data'], {
          'date': '2026-10-01',
          'source': 'alarm',
        });
        final screen = RingStartRecorder(
          open: () async => service,
          push: push,
          now: () => now.add(const Duration(minutes: 1)),
        );
        expect(await screen.record(), isTrue);
        expect(pushed, hasLength(1));
        expect(native.events.first['kind'], 'ring_screen_opened');
        // The first ring of the day is the one on record.
        expect((await RingStartedStore.load())?['at'], isoWithOffset(now));
      },
    );

    test('a failing push is swallowed and not logged as published', () async {
      SharedPreferences.setMockInitialValues({'github_token': 'ghp_x'});
      final recorder = RingStartRecorder(
        open: _open,
        push: (_, _) async => throw Exception('offline'),
        now: () => now,
      );
      expect(await recorder.record(), isFalse);
      expect(native.events.map((e) => e['kind']), ['ring_screen_opened']);
    });

    test('no channel at all still records and never throws', () async {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(native.channel, null);
      expect(await RingStartRecorder(now: () => now).record(), isFalse);
      expect(await RingStartedStore.load(), isNotNull);
    });
  });
}
