import 'package:flutter_test/flutter_test.dart';
import 'package:wake_alarm_sync/services/google_sign_in_backend.dart';

void main() {
  group('googleIdToken', () {
    test('returns the token the sign-in function yields', () async {
      // The injected path: proves the closure is what feeds crdt_sync, and
      // that no platform channel is touched to get there.
      expect(
        await googleIdToken(signInFn: () async => 'a-token'),
        'a-token',
      );
    });

    test('passes a null cancellation straight through', () async {
      // Dismissing the picker is an ordinary outcome, not an error: the
      // caller falls back to the password path.
      expect(await googleIdToken(signInFn: () async => null), isNull);
    });

    test('reports "not configured" when the client id is missing', () async {
      // Passed explicitly rather than relying on the const: an app whose
      // client id is filled in would otherwise reach the real plugin here.
      // The behaviour under test is the empty-id fallback itself.
      expect(await googleIdToken(serverClientId: ''), isNull);
    });

    test('pins the uid the security rules expect', () {
      // If this ever drifts from database.rules.json, a Google sign-in would
      // be accepted here and then denied every read and write.
      expect(kSyncUid, 'OvA2REQyLIhAHOEjzwS1o877rgG3');
    });
  });
}
