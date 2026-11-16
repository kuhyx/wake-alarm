import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:wake_alarm_sync/services/session_publisher.dart';

import '../fake_secure_storage.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  test('a failed publish reaches debugPrint, not only developer.log', () async {
    SharedPreferences.setMockInitialValues({});
    installFakeSecureStorage(initial: {'github_token': 'tok'});
    final lines = <String>[];
    final saved = debugPrint;
    debugPrint = (message, {wrapWidth}) => lines.add('$message');
    addTearDown(() => debugPrint = saved);

    final status = await SessionPublisher(
      open: () async => throw Exception('boom'),
    ).publish();

    expect(status, 'Session kept locally (sync failed)');
    expect(
      lines.join('\n'),
      contains('session publish failed: Exception: boom'),
    );
  });
}
