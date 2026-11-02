import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wake_alarm_sync/services/google_sign_in_backend.dart';

const _channel = MethodChannel('dev.kuhy/google_account_token');

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  tearDown(() {
    debugDefaultTargetPlatformOverride = null;
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(_channel, null);
  });

  group('googleIdToken', () {
    test('returns the token the sign-in function yields', () async {
      // The injected path: proves the closure is what feeds crdt_sync, and
      // that no platform channel is touched to get there.
      expect(await googleIdToken(signInFn: () async => 'a-token'), 'a-token');
    });

    test('passes a null cancellation straight through', () async {
      // Dismissing the picker is an ordinary outcome, not an error: the
      // caller falls back to the password path.
      expect(await googleIdToken(signInFn: () async => null), isNull);
    });

    test('reports "not configured" when the client id is missing', () async {
      // An empty client id must fall back rather than reach the OS chooser.
      debugDefaultTargetPlatformOverride = TargetPlatform.android;
      expect(await googleIdToken(serverClientId: ''), isNull);
    });

    test('asks the account-token plugin for the Web client id', () async {
      // The real path: the plugin's channel gets the pinned Web client id.
      debugDefaultTargetPlatformOverride = TargetPlatform.android;
      Object? sent;
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(_channel, (call) async {
            sent = call.arguments;
            return 'plugin-token';
          });
      expect(await googleIdToken(), 'plugin-token');
      expect(sent, {'serverClientId': kServerClientId});
    });

    test('pins the uid the security rules expect', () {
      // If this ever drifts from database.rules.json, a Google sign-in would
      // be accepted here and then denied every read and write.
      expect(kSyncUid, 'OvA2REQyLIhAHOEjzwS1o877rgG3');
    });
  });
}
