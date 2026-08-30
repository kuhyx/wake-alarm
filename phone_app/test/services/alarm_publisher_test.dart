import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:wake_alarm_sync/services/alarm_publisher.dart';

import '../fake_secure_storage.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    installFakeSecureStorage();
    SharedPreferences.setMockInitialValues(<String, Object>{});
  });

  test('an unconfigured install is told to connect a backend', () async {
    final message = await AlarmPublisher().publish(
      service: null,
      hour: 8,
      minute: 0,
    );
    expect(message, contains('Connect a sync backend'));
  });

  test('a missing store is not reported as a missing backend', () async {
    // The regression this guards. Both causes used to return the same
    // "connect a backend" line, so a store that failed to open looked like a
    // setup step the user had never done — while Firebase was connected the
    // whole time and the real fault was a null service. The advice pointed at
    // something that was not broken, and nothing published for weeks.
    SharedPreferences.setMockInitialValues(<String, Object>{
      'github_token': 'ghp_configured',
    });
    final message = await AlarmPublisher().publish(
      service: null,
      hour: 8,
      minute: 0,
    );
    expect(message, isNot(contains('Connect a sync backend')));
    expect(message, contains('Sync store unavailable'));
  });
}
