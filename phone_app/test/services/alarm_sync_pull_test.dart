import 'dart:convert';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wake_alarm_sync/services/alarm_sync_service.dart';

import '../e2e_support.dart';

const _deviceId = 'this-install';
const _peerId = 'previous-install';
const _old = 'wake-alarm-sync/devices';
const _prefix = 'wake-alarm-sync/devices-e2e';

class _MemPersistence implements LogPersistence {
  String? text;

  @override
  Future<String?> read() async => text;

  @override
  Future<void> write(String value) async => text = value;
}

Map<String, dynamic> _peerRecord(Map<String, Object?> fields, String hlc) => {
  'alarm': {
    'id': 'alarm',
    'fields': {
      for (final e in fields.entries) e.key: [e.value, hlc],
    },
    'deleted': false,
    'deleted_hlc': null,
  },
};

void main() {
  late AlarmSyncService service;

  setUp(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    installE2eTestStorage();
    service = await AlarmSyncService.open(
      persistence: _MemPersistence(),
      deviceId: _deviceId,
    );
  });

  test('setLocal keeps fields another writer put on the record', () async {
    final hlc = Hlc.newTick(_deviceId, wallTimeMsOverride: 1000);
    await service.setFields({
      'nfc_tag_ids': <String>['a', 'b'],
    }, hlc);
    await service.setLocal(6, 30);

    expect(service.currentAlarm, (hour: 6, minute: 30));
    final tags = service.field('nfc_tag_ids');
    expect(tags?.$1, ['a', 'b']);
    expect(tags?.$2, hlc);
  });

  test('field is null for an unset field or an empty record', () async {
    expect(service.field('nfc_tag_ids'), isNull);
    await service.setLocal(6, 30);
    expect(service.field('nfc_tag_ids'), isNull);
  });

  test('pushWith pulls a previous install and takes its newer field', () async {
    await service.setLocal(8, 0);
    // The previous install never updated: its record sits in plaintext on
    // the old prefix and reaches this one through the one-time E2E copy.
    final remote = MemGitHub({
      '$_old/$_peerId/alarm.json': jsonEncode(
        _peerRecord({
          'alarm_hour': 7,
          'alarm_minute': 0,
          'nfc_tag_ids': ['x', 'y'],
        }, '2026-09-11T10:26:18.254Z-0000-$_peerId'),
      ),
    });
    final github = remote.client();
    await service.pushWith(github);

    // The peer's tags are merged in; the peer's older alarm loses to the
    // fresh local one.
    expect(service.field('nfc_tag_ids')?.$1, ['x', 'y']);
    expect(service.currentAlarm, (hour: 8, minute: 0));
    // And the merged result is what was pushed, under this install's path.
    const path = '$_prefix/$_deviceId/alarm.json';
    expect(remote.files[path], isNot(contains('nfc_tag_ids')));
    final pushed = jsonDecode((await remote.opened(path))!) as Map;
    final fields = (pushed['alarm'] as Map)['fields'] as Map;
    expect((fields['nfc_tag_ids'] as List).first, ['x', 'y']);
    expect((fields['alarm_hour'] as List).first, 8);
    // The old plaintext node is copied, never rewritten.
    expect(remote.putPaths.where((p) => p.startsWith('$_old/')), isEmpty);
  });

  test('pushWith with no peers pushes the local log unchanged', () async {
    await service.setLocal(8, 0);
    final remote = MemGitHub();

    await service.pushWith(remote.client());

    expect(remote.putPaths, contains('$_prefix/$_deviceId/alarm.json'));
    expect(service.field('nfc_tag_ids'), isNull);
  });
}
