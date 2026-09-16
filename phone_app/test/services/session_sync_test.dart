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
import 'package:wake_alarm_sync/services/settings_sync.dart';

class _MemPersistence implements LogPersistence {
  String? text;

  @override
  Future<String?> read() async => text;

  @override
  Future<void> write(String value) async => text = value;
}

Future<AlarmSyncService> _open() =>
    AlarmSyncService.open(persistence: _MemPersistence(), deviceId: 'me');

MorningSession _session(DateTime at, {double? kg}) => SessionRules.start(
  now: at,
  tags: const SessionTagSettings(),
  nfcAvailable: false,
)..weightKg = kg;

Hlc _at(DateTime when) =>
    Hlc.newTick('peer', wallTimeMsOverride: when.millisecondsSinceEpoch);

void main() {
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  group('stageSessionData', () {
    test('stages nothing from an install with nothing to say', () async {
      final service = await _open();
      await stageSessionData(service);
      expect(service.field(sessionTagsField), isNull);
      expect(service.field(sessionsField), isNull);
      expect(service.field(latestWeightField), isNull);
    });

    test('stages tags, the history and the latest weight', () async {
      await SessionTagSettings.saveTagAt(SessionTagSlot.desk, 'd1');
      final store = SessionStore();
      await store.archive(_session(DateTime(2026, 9, 16, 8), kg: 71));
      await store.archive(_session(DateTime(2026, 9, 17, 8)));
      final service = await _open();
      await stageSessionData(service);
      expect(service.field(sessionTagsField)?.$1, <String>['', '', 'd1']);
      expect(sessionsOnRecord(service).map((s) => s.date), <String>[
        '2026-09-17',
        '2026-09-16',
      ]);
      expect(service.field(latestWeightField)?.$1, <String, Object?>{
        'date': '2026-09-16',
        'kg': 71.0,
      });
    });

    test('an unchanged history is not restaged', () async {
      await SessionStore().archive(_session(DateTime(2026, 9, 17, 8), kg: 70));
      final service = await _open();
      await stageSessionData(service);
      final first = service.field(sessionsField)!.$2;
      await stageSessionData(service);
      expect(service.field(sessionsField)!.$2, first);
    });

    test('rides along with the ring settings', () async {
      await SessionStore().archive(_session(DateTime(2026, 9, 17, 8)));
      final service = await _open();
      await stageLocalSettings(service);
      expect(service.field(sessionsField), isNotNull);
    });
  });

  group('applySyncedSessionData', () {
    test('restores tags and merges sessions from the record', () async {
      final service = await _open();
      final when = DateTime(2026, 9, 17, 9);
      await service.setFields(<String, Object?>{
        sessionTagsField: <String>['b', 'w', 'd'],
        sessionsField: <Object?>[
          _session(DateTime(2026, 9, 15, 8), kg: 69).toJson(),
          'junk',
        ],
      }, _at(when));
      await applySyncedSettings(service);
      final tags = await SessionTagSettings.load();
      expect(tags.tagIds, <String>['b', 'w', 'd']);
      expect(tags.editedAt, stampOf(_at(when)));
      final history = await SessionStore().history();
      expect(history.single.date, '2026-09-15');
      expect(history.single.weightKg, 69);
    });

    test('a local registration newer than the record wins', () async {
      await SessionTagSettings.saveTagAt(SessionTagSlot.bathroom, 'mine');
      final service = await _open();
      await service.setFields(<String, Object?>{
        sessionTagsField: <String>['theirs', '', ''],
      }, _at(DateTime(2020)));
      await applySyncedSessionData(service);
      expect(
        (await SessionTagSettings.load()).tagAt(SessionTagSlot.bathroom),
        'mine',
      );
    });

    test('a malformed tag list is left alone', () async {
      final service = await _open();
      await service.setFields(<String, Object?>{
        sessionTagsField: 'not a list',
      }, _at(DateTime(2026, 9, 17)));
      await applySyncedSessionData(service);
      expect((await SessionTagSettings.load()).isConfigured, isFalse);
    });
  });
}
