import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wake_alarm_sync/services/google_sign_in_backend.dart';

void main() {
  tearDown(() => debugDefaultTargetPlatformOverride = null);

  test('the one-tap button is hidden off Android', () {
    // flutter_test defaults to Android, so pin Linux (the desktop build): no
    // AccountManager, so the password path stays the only option.
    debugDefaultTargetPlatformOverride = TargetPlatform.linux;
    expect(googleSignInSupported, isFalse);
  });

  test('the one-tap button shows on Android', () {
    debugDefaultTargetPlatformOverride = TargetPlatform.android;
    expect(googleSignInSupported, isTrue);
  });
}
