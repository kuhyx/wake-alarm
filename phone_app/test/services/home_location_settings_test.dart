import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:wake_alarm_sync/services/home_location_settings.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  test('a fresh install has no home, which is not the same as away', () async {
    final home = await HomeLocationSettings.load();
    expect(home.isConfigured, isFalse);
    expect(home.hasCoordinate, isFalse);
    expect(home.radiusMeters, HomeLocationSettings.defaultRadiusMeters);
  });

  test('capture round-trips every field', () async {
    await HomeLocationSettings.capture(
      ssid: 'Orange_Home',
      bssid: 'CC:00:F1:AE:D6:C4',
      lat: 52.2291,
      lon: 20.9512,
    );
    final home = await HomeLocationSettings.load();
    expect(home.ssid, 'Orange_Home');
    expect(home.bssids, <String>['cc:00:f1:ae:d6:c4']);
    expect(home.lat, closeTo(52.2291, 1e-6));
    expect(home.hasCoordinate, isTrue);
    expect(home.isConfigured, isTrue);
  });

  test('a second capture adds a band rather than replacing it', () async {
    await HomeLocationSettings.capture(
      ssid: 'Home',
      bssid: 'aa:bb:cc:dd:ee:01',
    );
    await HomeLocationSettings.capture(
      ssid: 'Home',
      bssid: 'aa:bb:cc:dd:ee:02',
    );
    final home = await HomeLocationSettings.load();
    expect(home.bssids, hasLength(2));
    expect(home.matchesWifi(bssid: 'AA:BB:CC:DD:EE:02'), isTrue);
  });

  test('the same band captured twice is stored once', () async {
    await HomeLocationSettings.capture(bssid: 'aa:bb:cc:dd:ee:01');
    await HomeLocationSettings.capture(bssid: 'AA:BB:CC:DD:EE:01');
    final home = await HomeLocationSettings.load();
    expect(home.bssids, hasLength(1));
  });

  test('capture keeps a coordinate a later Wi-Fi-only capture omits', () async {
    await HomeLocationSettings.capture(lat: 52.5, lon: 21.5);
    await HomeLocationSettings.capture(ssid: 'Home');
    final home = await HomeLocationSettings.load();
    expect(home.hasCoordinate, isTrue);
    expect(home.ssid, 'Home');
  });

  test('the SSID matches whichever band the phone roamed onto', () {
    const home = HomeLocationSettings(
      ssid: 'Home',
      bssids: <String>['aa:bb:cc:dd:ee:01'],
    );
    // The 5 GHz radio was never captured, but it broadcasts the same name.
    expect(home.matchesWifi(ssid: 'Home', bssid: 'aa:bb:cc:dd:ee:99'), isTrue);
    expect(
      home.matchesWifi(ssid: 'Hotel', bssid: '11:22:33:44:55:66'),
      isFalse,
    );
    expect(home.matchesWifi(), isFalse);
  });

  test('clear returns the app to the strict sequence', () async {
    await HomeLocationSettings.capture(ssid: 'Home');
    await HomeLocationSettings.clear();
    expect((await HomeLocationSettings.load()).isConfigured, isFalse);
  });

  test('a malformed record reads as unconfigured, never as away', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{
      HomeLocationSettings.kKey: 'not json',
    });
    expect((await HomeLocationSettings.load()).isConfigured, isFalse);
  });
}
