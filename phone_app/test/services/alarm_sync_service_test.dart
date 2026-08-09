import 'dart:convert';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart' as http_testing;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uuid/uuid.dart';
import 'package:wake_alarm_sync/services/alarm_sync_service.dart';

const _deviceId = 'test-device-uuid';
const _alarmPath = 'wake-alarm-sync/devices/$_deviceId/alarm.json';

http.Response _response(int statusCode, [Object? jsonBody]) =>
    http.Response(jsonEncode(jsonBody ?? {}), statusCode);

/// In-memory persistence so the store never touches the real documents dir.
class _MemPersistence implements LogPersistence {
  String? text;

  @override
  Future<String?> read() async => text;

  @override
  Future<void> write(String value) async => text = value;
}

class _PutCall {
  _PutCall(this.path, this.body);
  final String path;
  final Map<String, dynamic> body;
}

/// Mock GitHub Contents API: GET `.../contents/<key>` returns
/// [contentResponses]`[key]` (404 if absent), the bare repo-existence GET
/// always succeeds, and every PUT is recorded. Mirrors the workout_app test.
({http.Client httpClient, List<_PutCall> putCalls}) _mockGitHub({
  Map<String, http.Response> contentResponses = const {},
}) {
  final putCalls = <_PutCall>[];
  final client = http_testing.MockClient((request) async {
    final path = request.url.path;
    if (!path.contains('/contents/')) return _response(200);
    final key = path.split('/contents/').last;
    if (request.method == 'PUT') {
      putCalls.add(
        _PutCall(key, jsonDecode(request.body) as Map<String, dynamic>),
      );
      return _response(200);
    }
    return contentResponses[key] ?? _response(404);
  });
  return (httpClient: client, putCalls: putCalls);
}

Map<String, dynamic> _decodePush(_PutCall call) =>
    jsonDecode(utf8.decode(base64.decode(call.body['content'] as String)))
        as Map<String, dynamic>;

void main() {
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
    final (:httpClient, :putCalls) = _mockGitHub();

    await service.push('tok', httpClient: httpClient);

    expect(putCalls, hasLength(1));
    expect(putCalls.single.path, _alarmPath);
    final pushed = _decodePush(putCalls.single);
    final fields = (pushed['alarm'] as Map<String, dynamic>)['fields']
        as Map<String, dynamic>;
    expect((fields['alarm_hour'] as List).first, 7);
    expect((fields['alarm_minute'] as List).first, 15);
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
      final paths = <String>[];
      final client = http_testing.MockClient((request) async {
        paths.add(request.url.path);
        return _response(200);
      });

      await service.push('tok', httpClient: client);

      expect(paths.any((path) => path.contains('devices/uuid-abc/')), isTrue);
      expect(
        paths.any(
          (path) =>
              path.contains('devices/${AlarmSyncService.legacyDeviceId}/'),
        ),
        isFalse,
      );
    });
  });
}
