import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:wake_alarm_sync/services/alarm_scheduler.dart';
import 'package:wake_alarm_sync/services/home_location_settings.dart';
import 'package:wake_alarm_sync/services/home_presence.dart';

const HomeLocationSettings _home = HomeLocationSettings(
  ssid: 'Orange_Home',
  bssids: <String>['cc:00:f1:ae:d6:c4'],
  lat: 52.2291,
  lon: 20.9512,
);

Map<String, Object?> _reading({
  String? ssid,
  String? bssid,
  double? distance,
  double? accuracy,
  String reason = 'ok',
}) => <String, Object?>{
  'ssid': ssid,
  'bssid': bssid,
  'lat': distance == null ? null : 52.0,
  'lon': distance == null ? null : 21.0,
  'accuracy': accuracy,
  'distanceMeters': distance,
  'reason': reason,
};

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('decide', () {
    test('the home SSID is home', () {
      final verdict = HomePresence.decide(_home, _reading(ssid: 'Orange_Home'));
      expect(verdict.state, PresenceState.home);
      expect(verdict.skipsTags, isFalse);
    });

    test('a captured BSSID is home even under a different name', () {
      final verdict = HomePresence.decide(
        _home,
        _reading(ssid: 'Orange_Home_5G', bssid: 'CC:00:F1:AE:D6:C4'),
      );
      expect(verdict.state, PresenceState.home);
    });

    test('a redacted BSSID is not a match', () {
      // Kotlin filters 02:00:00:00:00:00 to null; if it ever leaked through
      // as a literal it must still not match a captured address.
      final verdict = HomePresence.decide(
        _home,
        _reading(bssid: '02:00:00:00:00:00'),
      );
      expect(verdict.state, PresenceState.away);
    });

    test("someone else's Wi-Fi is away, and says so", () {
      final verdict = HomePresence.decide(_home, _reading(ssid: 'Hotel_Guest'));
      expect(verdict.state, PresenceState.away);
      expect(verdict.detail, contains('Hotel_Guest'));
    });

    test('inside the radius is home', () {
      final verdict = HomePresence.decide(_home, _reading(distance: 40));
      expect(verdict.state, PresenceState.home);
    });

    test('outside the radius is away, in readable units', () {
      final verdict = HomePresence.decide(_home, _reading(distance: 25712));
      expect(verdict.state, PresenceState.away);
      expect(verdict.detail, contains('26 km'));
    });

    test('a coarse fix counts in the user favour, not against it', () {
      // 200 m away with a 100 m error circle and a 150 m radius: the fix
      // cannot distinguish home from not-home, and erring towards the strict
      // sequence at home is the safe direction for a wake-up alarm.
      final verdict = HomePresence.decide(
        _home,
        _reading(distance: 200, accuracy: 100),
      );
      expect(verdict.state, PresenceState.home);
    });

    test('a coarse fix still cannot rescue a different city', () {
      final verdict = HomePresence.decide(
        _home,
        _reading(distance: 25712, accuracy: 500),
      );
      expect(verdict.state, PresenceState.away);
    });

    test('nothing readable is away, naming the cause', () {
      for (final (reason, text) in <(String, String)>[
        ('no-permission', 'permission'),
        ('location-disabled', 'services are off'),
        ('no-fix', 'no location fix'),
      ]) {
        final verdict = HomePresence.decide(_home, _reading(reason: reason));
        expect(verdict.state, PresenceState.away, reason: reason);
        expect(verdict.detail, contains(text));
      }
    });

    test('a null reading is away, never a crash', () {
      expect(HomePresence.decide(_home, null).state, PresenceState.away);
    });

    test('a distance without a stored coordinate falls through', () {
      const wifiOnly = HomeLocationSettings(ssid: 'Orange_Home');
      final verdict = HomePresence.decide(wifiOnly, _reading(distance: 40));
      expect(verdict.state, PresenceState.away);
    });
  });

  group('resolve', () {
    setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

    void mockChannel(Object? Function() reading) {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(
            const MethodChannel(AlarmScheduler.channelName),
            (call) async =>
                call.method == 'readPresence' ? reading() : null,
          );
    }

    test('an unregistered home stays on the strict sequence', () async {
      var called = false;
      mockChannel(() {
        called = true;
        return _reading(ssid: 'Hotel_Guest');
      });
      final verdict = await HomePresence().resolve();
      expect(verdict.state, PresenceState.home);
      expect(verdict.skipsTags, isFalse);
      // The whole point: no home, no channel call, no permission needed.
      expect(called, isFalse);
    });

    test('a registered home consults the platform', () async {
      await HomeLocationSettings.capture(ssid: 'Orange_Home');
      mockChannel(() => _reading(ssid: 'Orange_Home'));
      expect((await HomePresence().resolve()).state, PresenceState.home);
    });

    test('a platform error is away, not an exception', () async {
      await HomeLocationSettings.capture(ssid: 'Orange_Home');
      mockChannel(() => throw PlatformException(code: 'boom'));
      final verdict = await HomePresence().resolve();
      expect(verdict.state, PresenceState.away);
    });

    test('a missing platform is away', () async {
      await HomeLocationSettings.capture(ssid: 'Orange_Home');
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(
            const MethodChannel(AlarmScheduler.channelName),
            null,
          );
      expect((await HomePresence().resolve()).state, PresenceState.away);
    });
  });
}
