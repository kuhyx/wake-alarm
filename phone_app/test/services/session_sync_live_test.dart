import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:wake_alarm_sync/services/alarm_sync_service.dart';
import 'package:wake_alarm_sync/services/morning_session.dart';
import 'package:wake_alarm_sync/services/session_json.dart';
import 'package:wake_alarm_sync/services/session_rules.dart';
import 'package:wake_alarm_sync/services/session_store.dart';
import 'package:wake_alarm_sync/services/session_sync.dart';
import 'package:wake_alarm_sync/services/session_tag_settings.dart';

/// The live-session and energy halves of `session_sync.dart`: what the PC
/// reads to tell "started, not finished" from "never started".
class _MemPersistence implements LogPersistence {
  String? text;

  @override
  Future<String?> read() async => text;

  @override
  Future<void> write(String value) async => text = value;
}

Future<AlarmSyncService> _open() =>
    AlarmSyncService.open(persistence: _MemPersistence(), deviceId: 'me');

MorningSession _session(DateTime at, {int? energy}) => SessionRules.start(
  now: at,
  tags: const SessionTagSettings(),
  nfcAvailable: false,
)..energy = energy;

void main() {
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  group('current_session', () {
    test('a live session is staged even with no history yet', () async {
      final store = SessionStore();
      await store.save(_session(DateTime(2026, 9, 19, 8, 1)));
      final service = await _open();
      await stageSessionData(service);
      final live = service.field(currentSessionField)?.$1;
      expect(live, isA<Map<Object?, Object?>>());
      expect((live! as Map)['outcome'], 'active');
      expect(service.field(sessionsField), isNull);
    });

    test('is cleared with a newer stamp once archived', () async {
      final store = SessionStore();
      final session = _session(DateTime(2026, 9, 19, 8, 1));
      await store.save(session);
      final service = await _open();
      await stageSessionData(service);
      final liveStamp = service.field(currentSessionField)!.$2;
      session
        ..outcome = SessionOutcome.completed
        ..updatedAt = DateTime(2026, 9, 19, 8, 40);
      await store.archive(session);
      await stageSessionData(service);
      final cleared = service.field(currentSessionField)!;
      expect(cleared.$1, isEmpty);
      expect(cleared.$2.wallTimeMs, greaterThan(liveStamp.wallTimeMs));
    });

    test('is never applied from a peer', () async {
      final service = await _open();
      await service.setFields(<String, Object?>{
        currentSessionField: _session(DateTime(2026, 9, 19, 8, 1)).toJson(),
      }, Hlc.newTick('peer'));
      await applySyncedSessionData(service);
      expect(await SessionStore().loadCurrent(), isNull);
    });
  });

  group('latest_energy', () {
    test('ships the newest rated morning', () async {
      final store = SessionStore();
      await store.archive(_session(DateTime(2026, 9, 18, 8), energy: 2));
      await store.archive(_session(DateTime(2026, 9, 19, 8)));
      final service = await _open();
      await stageSessionData(service);
      expect(service.field(latestEnergyField)?.$1, <String, Object?>{
        'date': '2026-09-18',
        'level': 2,
      });
    });

    test('is absent until a morning was rated', () async {
      await SessionStore().archive(_session(DateTime(2026, 9, 19, 8)));
      final service = await _open();
      await stageSessionData(service);
      expect(service.field(latestEnergyField), isNull);
    });

    test('survives the JSON round trip', () {
      final json = _session(DateTime(2026, 9, 19, 8), energy: 4).toJson();
      expect(json['energy'], 4);
      expect(sessionFromJson(json)?.energy, 4);
    });
  });
}
