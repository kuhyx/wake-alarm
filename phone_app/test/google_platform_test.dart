import 'package:flutter_test/flutter_test.dart';
import 'package:wake_alarm_sync/services/google_sign_in_backend.dart';

void main() {
  test('reports whether the programmatic Google flow exists here', () {
    // Android is the only platform shipping it. Asked as a platform question
    // rather than of the plugin, because GoogleSignIn.supportsAuthenticate()
    // itself throws UnimplementedError where no implementation is registered
    // -- an Error, not an Exception, so it would escape an ordinary catch and
    // take down the settings screen's build(). The test host is Linux, so
    // this is false here and the password path stays visible.
    expect(googleSignInSupported, isFalse);
  });
}
