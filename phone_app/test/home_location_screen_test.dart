import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:wake_alarm_sync/screens/home_location_screen.dart';
import 'package:wake_alarm_sync/services/alarm_scheduler.dart';
import 'package:wake_alarm_sync/services/home_location_settings.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  Map<String, Object?>? presence;

  setUp(() {
    presence = null;
    SharedPreferences.setMockInitialValues(<String, Object>{});
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
          const MethodChannel(AlarmScheduler.channelName),
          (call) async => call.method == 'readPresence' ? presence : null,
        );
  });

  Future<void> pumpScreen(WidgetTester tester) async {
    await tester.pumpWidget(
      const MaterialApp(home: HomeLocationScreen()),
    );
    await tester.pump();
  }

  testWidgets('a fresh install shows nothing captured', (tester) async {
    await pumpScreen(tester);
    expect(find.text('not captured'), findsNWidgets(2));
    expect(find.text('none'), findsOneWidget);
  });

  testWidgets('capture stores what the platform reported', (tester) async {
    presence = <String, Object?>{
      'ssid': 'Orange_Home',
      'bssid': 'CC:00:F1:AE:D6:C4',
      'lat': 52.2291,
      'lon': 20.9512,
      'reason': 'ok',
    };
    await pumpScreen(tester);
    await tester.tap(find.text('Capture this place as home'));
    await tester.pumpAndSettle();

    expect(find.textContaining('Captured Wi-Fi'), findsOneWidget);
    final home = await HomeLocationSettings.load();
    expect(home.ssid, 'Orange_Home');
    expect(home.bssids, <String>['cc:00:f1:ae:d6:c4']);
    expect(home.hasCoordinate, isTrue);
  });

  testWidgets('a Wi-Fi-only capture says the GPS fallback is unset', (
    tester,
  ) async {
    presence = <String, Object?>{'ssid': 'Orange_Home', 'reason': 'ok'};
    await pumpScreen(tester);
    await tester.tap(find.text('Capture this place as home'));
    await tester.pumpAndSettle();

    expect(find.textContaining('GPS fallback is unset'), findsOneWidget);
    expect((await HomeLocationSettings.load()).hasCoordinate, isFalse);
  });

  testWidgets('a denied permission says so instead of capturing nothing', (
    tester,
  ) async {
    presence = <String, Object?>{'reason': 'no-permission'};
    await pumpScreen(tester);
    await tester.tap(find.text('Capture this place as home'));
    await tester.pumpAndSettle();

    expect(find.textContaining('Grant location permission'), findsOneWidget);
    expect((await HomeLocationSettings.load()).isConfigured, isFalse);
  });

  testWidgets('forget home returns to the strict sequence', (tester) async {
    await HomeLocationSettings.capture(ssid: 'Orange_Home');
    await pumpScreen(tester);
    await tester.tap(find.text('Forget home'));
    await tester.pumpAndSettle();

    expect(find.textContaining('full sequence now applies'), findsOneWidget);
    expect((await HomeLocationSettings.load()).isConfigured, isFalse);
  });
}
