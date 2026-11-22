import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:wake_alarm_sync/services/firebase_backend.dart';
import 'package:wake_alarm_sync/services/sync_emulator.dart';

/// A [RemoteStore] that is only ever compared by identity.
class _Github extends Fake implements RemoteStore {}

void main() {
  test(
    'a build without the define syncs to prod, never the emulator',
    () async {
      expect(kSyncEmulatorUrl, isEmpty);
      expect(syncEmulatorOn, isFalse);
      expect(kProject.databaseUrl, contains('kuhy-syncs'));
      final github = _Github();
      // No Firebase session in tests: prod's rollback path, GitHub alone.
      expect(await syncBackend(github), same(github));
    },
  );

  test('the emulator client signs as owner against the given origin', () async {
    final seen = <Uri>[];
    final client = emulatorClient(
      url: 'http://10.0.2.2:9000',
      httpClient: MockClient((request) async {
        seen.add(request.url);
        return http.Response('null', 200);
      }),
    );
    await client.listDirectory('wake-alarm-sync/devices-e2e');
    expect(seen.single.origin, 'http://10.0.2.2:9000');
    expect(seen.single.queryParameters['auth'], 'owner');
    expect(await EmulatorTokenProvider().hasSession(), isTrue);
    expect(emulatorAccount.email, 'emulator');
  });
}
