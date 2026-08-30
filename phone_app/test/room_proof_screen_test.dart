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

  testWidgets('shows both slots unregistered on a fresh install', (
    tester,
  ) async {
    await tester.pumpWidget(const MaterialApp(home: RoomProofScreen()));
    await tester.pumpAndSettle();
    expect(find.textContaining('none registered'), findsNWidgets(2));
    expect(find.text('Register tag 1'), findsOneWidget);
    expect(find.text('Register tag 2'), findsOneWidget);
  });

  testWidgets('starting a scan puts the reader into waiting state', (
    tester,
  ) async {
    await tester.pumpWidget(const MaterialApp(home: RoomProofScreen()));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Register tag 1'));
    await tester.pumpAndSettle();

    expect(calls, contains('startTagRegistration'));
    expect(find.textContaining('Tap tag 1'), findsOneWidget);
  });

  testWidgets('only the scanning row is disabled while waiting', (
    tester,
  ) async {
    await tester.pumpWidget(const MaterialApp(home: RoomProofScreen()));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Register tag 2'));
    await tester.pumpAndSettle();

    expect(find.text('Waiting for tag…'), findsOneWidget);
    final other = tester.widget<FilledButton>(
      find.ancestor(
        of: find.text('Register tag 1'),
        matching: find.byType(FilledButton),
      ),
    );
    expect(other.onPressed, isNull, reason: 'one scan at a time');
  });

  testWidgets('says so when the device cannot scan, rather than waiting', (
    tester,
  ) async {
    nfcStarts = false;
    await tester.pumpWidget(const MaterialApp(home: RoomProofScreen()));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Register tag 1'));
    await tester.pumpAndSettle();

    expect(find.textContaining('unavailable'), findsOneWidget);
  });

  testWidgets('each registered tag is shown against its own slot', (
    tester,
  ) async {
    await RoomProofSettings.saveNfcTagAt(0, '04a2b3c4');
    await RoomProofSettings.saveNfcTagAt(1, '04ffee11');
    await tester.pumpWidget(const MaterialApp(home: RoomProofScreen()));
    await tester.pumpAndSettle();
    expect(find.text('Tag 1: 04a2b3c4'), findsOneWidget);
    expect(find.text('Tag 2: 04ffee11'), findsOneWidget);
    expect(find.text('Register tag 1 again'), findsOneWidget);
  });
}
