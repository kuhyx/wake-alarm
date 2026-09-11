import 'dart:convert';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart' as http_testing;
import 'package:wake_alarm_sync/services/alarm_sync_service.dart';

const _deviceId = 'this-install';
const _peerId = 'previous-install';
const _prefix = 'wake-alarm-sync/devices';

class _MemPersistence implements LogPersistence {
  String? text;

  @override
  Future<String?> read() async => text;

  @override
  Future<void> write(String value) async => text = value;
}

http.Response _json(Object body, [int status = 200]) =>
    http.Response(jsonEncode(body), status);

/// Mock GitHub Contents API with one peer directory holding [peerLog].
///
/// The directory GET answers the listing `syncLog` walks, the peer's file GET
/// answers the pull, and every PUT is recorded so the merged push can be
/// inspected.
({http.Client client, List<Map<String, dynamic>> pushes}) _mockRemote({
  Map<String, dynamic>? peerLog,
}) {
  final pushes = <Map<String, dynamic>>[];
  final client = http_testing.MockClient((request) async {
    final path = request.url.path;
    if (!path.contains('/contents/')) return _json({});
    final key = path.split('/contents/').last;
    if (request.method == 'PUT') {
      final body = jsonDecode(request.body) as Map<String, dynamic>;
      final text = utf8.decode(base64.decode(body['content'] as String));
      pushes.add(jsonDecode(text) as Map<String, dynamic>);
      return _json({});
    }
    if (key == _prefix) {
      return _json([
        if (peerLog != null) {'name': _peerId, 'type': 'dir'},
        {'name': _deviceId, 'type': 'dir'},
      ]);
    }
    if (key == '$_prefix/$_peerId/alarm.json' && peerLog != null) {
      return _json({
        'content': base64.encode(utf8.encode(jsonEncode(peerLog))),
        'encoding': 'base64',
      });
    }
    return _json({}, 404);
  });
  return (client: client, pushes: pushes);
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
    final (:client, :pushes) = _mockRemote(
      peerLog: _peerRecord({
        'alarm_hour': 7,
        'alarm_minute': 0,
        'nfc_tag_ids': ['x', 'y'],
      }, '2026-09-11T10:26:18.254Z-0000-$_peerId'),
    );
    final github = GitHubClient(
      owner: 'o',
      repo: 'r',
      token: 't',
      httpClient: client,
    );

    await service.pushWith(github);

    // The peer's tags are merged in; the peer's older alarm loses to the
    // fresh local one.
    expect(service.field('nfc_tag_ids')?.$1, ['x', 'y']);
    expect(service.currentAlarm, (hour: 8, minute: 0));
    // And the merged result is what was pushed, under this install's path.
    expect(pushes, hasLength(1));
    final fields = (pushes.single['alarm'] as Map)['fields'] as Map;
    expect((fields['nfc_tag_ids'] as List).first, ['x', 'y']);
    expect((fields['alarm_hour'] as List).first, 8);
  });

  test('pushWith with no peers pushes the local log unchanged', () async {
    await service.setLocal(8, 0);
    final (:client, :pushes) = _mockRemote();
    final github = GitHubClient(
      owner: 'o',
      repo: 'r',
      token: 't',
      httpClient: client,
    );

    await service.pushWith(github);

    expect(pushes, hasLength(1));
    expect(service.field('nfc_tag_ids'), isNull);
  });
}
