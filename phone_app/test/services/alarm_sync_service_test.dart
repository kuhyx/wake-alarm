import 'dart:convert';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart' as http_testing;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uuid/uuid.dart';
import 'package:wake_alarm_sync/services/alarm_sync_e2e.dart';
import 'package:wake_alarm_sync/services/alarm_sync_service.dart';

import '../e2e_support.dart';

const _deviceId = 'test-device-uuid';
const _alarmPath = 'wake-alarm-sync/devices-e2e/$_deviceId/alarm.json';

/// In-memory persistence so the store never touches the real documents dir.
class _MemPersistence implements LogPersistence {
  String? text;

  @override
  Future<String?> read() async => text;

  @override
  Future<void> write(String value) async => text = value;
}

void main() {
  setUp(() {
    TestWidgetsFlutterBinding.ensureInitialized();
    installE2eTestStorage();
  });

  test('currentAlarm is null before anything is set', () async {
    final service = await AlarmSyncService.open(
      persistence: _MemPersistence(),
      deviceId: _deviceId,
    );
    expect(service.currentAlarm, isNull);
  });

  test('setLocal stores the alarm locally and survives a reopen', () async {
    final persistence = _MemPersistence();
    final service = await AlarmSyncService.open(
      persistence: persistence,
      deviceId: _deviceId,
    );
    await service.setLocal(6, 30);
    expect(service.currentAlarm, (hour: 6, minute: 30));

    // The same persistence backend rehydrates the alarm on the next open.
    final reopened = await AlarmSyncService.open(
      persistence: persistence,
      deviceId: _deviceId,
    );
    expect(reopened.currentAlarm, (hour: 6, minute: 30));
  });

  test('push PUTs the alarm log to the phone device path', () async {
    final service = await AlarmSyncService.open(
      persistence: _MemPersistence(),
      deviceId: _deviceId,
    );
    await service.setLocal(7, 15);
    final remote = MemGitHub();

    await service.push('tok', httpClient: remote.httpClient);

    expect(remote.putPaths, contains(_alarmPath));
    expect(remote.files[_alarmPath], isNot(contains('alarm_hour')));
    final pushed =
        jsonDecode((await remote.opened(_alarmPath))!) as Map<String, dynamic>;
    final fields =
        (pushed['alarm'] as Map<String, dynamic>)['fields']
            as Map<String, dynamic>;
    expect((fields['alarm_hour'] as List).first, 7);
    expect((fields['alarm_minute'] as List).first, 15);
  });

  test('a device with no passphrase pushes nothing', () async {
    installE2eTestStorage(initial: {'crdt_sync_e2e_passphrase': ''});
    final service = await AlarmSyncService.open(
      persistence: _MemPersistence(),
      deviceId: _deviceId,
    );
    await service.setLocal(7, 15);
    final remote = MemGitHub();

    await expectLater(
      service.push('tok', httpClient: remote.httpClient),
      throwsA(isA<SyncLockedException>()),
    );
    expect(remote.putPaths, isEmpty);
    expect(alarmSyncLocked.value, isTrue);
    expect(
      const SyncLockedException(E2eLockReason.wrongKey).toString(),
      contains('wrongKey'),
    );
  });

  test('push is a network round-trip that swallows a server error', () async {
    final service = await AlarmSyncService.open(
      persistence: _MemPersistence(),
      deviceId: _deviceId,
    );
    await service.setLocal(9, 0);
    final client = http_testing.MockClient(
      (request) async => http.Response('', 500),
    );

    // A GitHubSyncError from the transport propagates as an Exception the UI
    // can catch; it must be a normal Exception, not an Error.
    await expectLater(
      service.push('tok', httpClient: client),
      throwsA(isA<Exception>()),
    );
  });

  group('device id', () {
    setUp(() => SharedPreferences.setMockInitialValues({}));

    test('mints and persists a uuid on first run', () async {
      final minted = await AlarmSyncService.loadDeviceId();

      expect(Uuid.isValidUUID(fromString: minted), isTrue);
      final prefs = await SharedPreferences.getInstance();
      expect(prefs.getString(AlarmSyncService.kDeviceIdKey), minted);
    });

    test('returns the same id on every later run', () async {
      final first = await AlarmSyncService.loadDeviceId();
      final second = await AlarmSyncService.loadDeviceId();

      expect(second, first);
    });

    test('adopts an id already stored under the shared key', () async {
      SharedPreferences.setMockInitialValues({
        AlarmSyncService.kDeviceIdKey: 'pre-existing-id',
      });

      expect(await AlarmSyncService.loadDeviceId(), 'pre-existing-id');
    });

    test('treats a blank stored id as absent and mints a new one', () async {
      SharedPreferences.setMockInitialValues({
        AlarmSyncService.kDeviceIdKey: '',
      });

      expect(await AlarmSyncService.loadDeviceId(), isNotEmpty);
    });

    test('pushes under the resolved uuid, not the legacy phone path', () async {
      final service = await AlarmSyncService.open(
        persistence: _MemPersistence(),
        deviceId: 'uuid-abc',
      );
      await service.setLocal(6, 30);
      final remote = MemGitHub();

      await service.push('tok', httpClient: remote.httpClient);

      final paths = remote.putPaths;
      expect(
        paths.any((path) => path.contains('devices-e2e/uuid-abc/')),
        isTrue,
      );
      expect(
        paths.any(
          (path) => path.contains('/${AlarmSyncService.legacyDeviceId}/'),
        ),
        isFalse,
      );
    });
  });
}
