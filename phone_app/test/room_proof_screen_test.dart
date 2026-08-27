import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:wake_alarm_sync/screens/room_proof_screen.dart';
import 'package:wake_alarm_sync/services/alarm_scheduler.dart';
import 'package:wake_alarm_sync/services/room_proof_settings.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late List<String> calls;
  late bool nfcStarts;
  late MethodChannel channel;

  setUp(() {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    calls = <String>[];
    nfcStarts = true;
    channel = const MethodChannel(AlarmScheduler.channelName);
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
          calls.add(call.method);
          if (call.method == 'startTagRegistration') return nfcStarts;
          return null;
        });
  });

  testWidgets('shows that no tag is registered on a fresh install', (
    tester,
  ) async {
    await tester.pumpWidget(const MaterialApp(home: RoomProofScreen()));
    await tester.pumpAndSettle();
    expect(find.textContaining('none registered'), findsOneWidget);
  });

  testWidgets('starting a scan puts the reader into waiting state', (
    tester,
  ) async {
    await tester.pumpWidget(const MaterialApp(home: RoomProofScreen()));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Register NFC tag'));
    await tester.pumpAndSettle();

    expect(calls, contains('startTagRegistration'));
    expect(find.textContaining('Tap the tag'), findsOneWidget);
  });

  testWidgets('says so when the device cannot scan, rather than waiting', (
    tester,
  ) async {
    nfcStarts = false;
    await tester.pumpWidget(const MaterialApp(home: RoomProofScreen()));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Register NFC tag'));
    await tester.pumpAndSettle();

    expect(find.textContaining('unavailable'), findsOneWidget);
  });

  testWidgets('saving a QR payload persists it', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: RoomProofScreen()));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'kitchen');
    await tester.tap(find.text('Save QR code'));
    await tester.pumpAndSettle();

    expect((await RoomProofSettings.load()).qrPayload, 'kitchen');
    expect(find.text('QR code saved.'), findsOneWidget);
  });

  testWidgets('a registered tag is shown when reopening the screen', (
    tester,
  ) async {
    await RoomProofSettings.saveNfcTag('04a2b3c4');
    await tester.pumpWidget(const MaterialApp(home: RoomProofScreen()));
    await tester.pumpAndSettle();
    expect(find.textContaining('04a2b3c4'), findsOneWidget);
  });
}
