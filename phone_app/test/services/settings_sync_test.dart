import 'dart:convert';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:wake_alarm_sync/services/alarm_sync_service.dart';
import 'package:wake_alarm_sync/services/home_location_settings.dart';
import 'package:wake_alarm_sync/services/ramp_progress.dart';
import 'package:wake_alarm_sync/services/room_proof_settings.dart';
import 'package:wake_alarm_sync/services/settings_sync.dart';

const _deviceId = 'this-install';

class _MemPersistence implements LogPersistence {
  String? text;

  @override
  Future<String?> read() async => text;

  @override
  Future<void> write(String value) async => text = value;
}

Future<AlarmSyncService> _open() =>
    AlarmSyncService.open(persistence: _MemPersistence(), deviceId: _deviceId);

Hlc _at(String iso) => Hlc.newTick(
  'peer',
  wallTimeMsOverride: DateTime.parse(iso).millisecondsSinceEpoch,
);

const _home = <String, Object?>{
  'ssid': 'HomeNet',
  'bssids': ['aa:bb:cc:dd:ee:ff'],
  'lat': 52.2,
  'lon': 20.9,
  'radiusMeters': 150.0,
};

void main() {
  group('stageLocalSettings', () {
    test('an untouched install contributes nothing', () async {
      SharedPreferences.setMockInitialValues({});
      final service = await _open();
      await stageLocalSettings(service);
      expect(service.field(nfcTagsField), isNull);
      expect(service.field(homeLocationField), isNull);
    });

    test('a stamped edit lands on the record at its edit time', () async {
      SharedPreferences.setMockInitialValues({});
      await RoomProofSettings.saveNfcTagAt(0, 'tag-a');
      final edited = (await RoomProofSettings.load()).editedAt;
      final service = await _open();

      await stageLocalSettings(service);

      final field = service.field(nfcTagsField);
      expect(field?.$1, ['tag-a', '']);
      expect(
        field?.$2.wallTimeMs,
        DateTime.parse(edited).toUtc().millisecondsSinceEpoch,
      );
    });

    test('a pre-stamp value goes in just above the epoch', () async {
      SharedPreferences.setMockInitialValues({
        RoomProofSettings.kNfcTagsKey: jsonEncode(['old-a', 'old-b']),
        HomeLocationSettings.kKey: jsonEncode(_home),
      });
      final service = await _open();

      await stageLocalSettings(service);

      expect(service.field(nfcTagsField)?.$2.wallTimeMs, 1);
      expect(service.field(homeLocationField)?.$2.wallTimeMs, 1);
      final home = service.field(homeLocationField)?.$1;
      expect(home, isA<Map<String, Object?>>());
      expect((home! as Map)['ssid'], 'HomeNet');
    });

    test('an older local edit does not overwrite a newer field', () async {
      SharedPreferences.setMockInitialValues({
        RoomProofSettings.kNfcTagsKey: jsonEncode(['local', '']),
        RoomProofSettings.kEditedAtKey: '2026-09-01T00:00:00.000Z',
      });
      final service = await _open();
      await service.setFields({
        nfcTagsField: ['remote', 'newer'],
      }, _at('2026-09-10T00:00:00.000Z'));

      await stageLocalSettings(service);

      expect(service.field(nfcTagsField)?.$1, ['remote', 'newer']);
    });
  });

  group('applySyncedSettings', () {
    test('a fresh install takes the record values with their stamps', () async {
      SharedPreferences.setMockInitialValues({});
      final service = await _open();
      await service.setFields({
        nfcTagsField: ['x', 'y'],
        homeLocationField: _home,
      }, _at('2026-09-11T10:26:18.254Z'));

      await applySyncedSettings(service);

      final tags = await RoomProofSettings.load();
      expect(tags.nfcTagIds, ['x', 'y']);
      expect(tags.editedAt, '2026-09-11T10:26:18.254Z');
      final home = await HomeLocationSettings.load();
      expect(home.ssid, 'HomeNet');
      expect(home.bssids, ['aa:bb:cc:dd:ee:ff']);
      expect(home.editedAt, '2026-09-11T10:26:18.254Z');
    });

    test('a newer local edit is kept over an older record', () async {
      SharedPreferences.setMockInitialValues({
        RoomProofSettings.kNfcTagsKey: jsonEncode(['mine', 'too']),
        RoomProofSettings.kEditedAtKey: '2026-09-12T00:00:00.000Z',
        HomeLocationSettings.kKey: jsonEncode(_home),
        HomeLocationSettings.kEditedAtKey: '2026-09-12T00:00:00.000Z',
      });
      final service = await _open();
      await service.setFields({
        nfcTagsField: ['old', 'old'],
        homeLocationField: <String, Object?>{'ssid': 'Elsewhere'},
      }, _at('2026-09-01T00:00:00.000Z'));

      await applySyncedSettings(service);

      expect((await RoomProofSettings.load()).nfcTagIds, ['mine', 'too']);
      expect((await HomeLocationSettings.load()).ssid, 'HomeNet');
    });

    test('a malformed value is ignored rather than applied', () async {
      SharedPreferences.setMockInitialValues({});
      final service = await _open();
      await service.setFields({
        nfcTagsField: 'not-a-list',
        homeLocationField: 42,
      }, _at('2026-09-11T00:00:00.000Z'));

      await applySyncedSettings(service);

      expect((await RoomProofSettings.load()).nfcTagIds, ['', '']);
      expect((await HomeLocationSettings.load()).isConfigured, isFalse);
    });

    test('a cleared home on the record clears a stale local one', () async {
      SharedPreferences.setMockInitialValues({
        HomeLocationSettings.kKey: jsonEncode(_home),
        HomeLocationSettings.kEditedAtKey: '2026-09-01T00:00:00.000Z',
      });
      final service = await _open();
      await service.setFields({
        homeLocationField: const HomeLocationSettings().toJson(),
      }, _at('2026-09-11T00:00:00.000Z'));

      await applySyncedSettings(service);

      expect((await HomeLocationSettings.load()).isConfigured, isFalse);
    });

    test('apply then stage is a no-op: nothing is pushed back', () async {
      SharedPreferences.setMockInitialValues({});
      final service = await _open();
      final hlc = _at('2026-09-11T10:26:18.254Z');
      await service.setFields({
        nfcTagsField: ['x', 'y'],
        homeLocationField: _home,
      }, hlc);

      await applySyncedSettings(service);
      await stageLocalSettings(service);

      expect(service.field(nfcTagsField)?.$2, hlc);
      expect(service.field(homeLocationField)?.$2, hlc);
    });
  });

  group('ramp earned dates', () {
    test('local dates are pushed as the union with the logged ones', () async {
      SharedPreferences.setMockInitialValues({});
      await RampProgress.merge({'2026-09-28'});
      final service = await _open();
      await service.setFields({
        rampEarnedField: ['2026-10-02'],
      }, _at('2026-10-02T08:00:00Z'));

      await stageLocalSettings(service);

      expect(service.field(rampEarnedField)?.$1, ['2026-09-28', '2026-10-02']);
    });

    test('nothing new locally means nothing pushed', () async {
      SharedPreferences.setMockInitialValues({});
      await RampProgress.merge({'2026-09-28'});
      final service = await _open();
      final hlc = _at('2026-10-02T08:00:00Z');
      await service.setFields({
        rampEarnedField: ['2026-09-28', '2026-10-02'],
      }, hlc);

      await stageLocalSettings(service);

      expect(service.field(rampEarnedField)?.$2, hlc);
    });

    test('a reinstall gets every earned date back', () async {
      SharedPreferences.setMockInitialValues({});
      final service = await _open();
      await service.setFields({
        rampEarnedField: ['2026-09-28', 'junk', 7],
      }, _at('2026-10-02T08:00:00Z'));

      await applySyncedSettings(service);

      expect(await RampProgress.load(), {'2026-09-28'});
    });

    test('a malformed field earns nothing', () async {
      SharedPreferences.setMockInitialValues({});
      final service = await _open();
      await service.setFields({
        rampEarnedField: 'not a list',
      }, _at('2026-10-02T08:00:00Z'));

      await applySyncedSettings(service);

      expect(await RampProgress.load(), isEmpty);
    });
  });
}
