import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:wake_alarm_sync/screens/room_proof_screen.dart';
import 'package:wake_alarm_sync/services/alarm_scheduler.dart';
import 'package:wake_alarm_sync/services/room_proof_settings.dart';
import 'package:wake_alarm_sync/ui/cues.dart';
import 'package:wake_alarm_sync/ui/dashed_slot.dart';

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
    expect(find.byType(DashedSlot), findsNWidgets(2));
    expect(find.byKey(const ValueKey<String>('register-0')), findsOneWidget);
    expect(find.byKey(const ValueKey<String>('register-1')), findsOneWidget);
  });

  testWidgets('starting a scan puts the reader into waiting state', (
    tester,
  ) async {
    await tester.pumpWidget(const MaterialApp(home: RoomProofScreen()));
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey<String>('register-0')));
    await tester.pump();

    expect(calls, contains('startTagRegistration'));
    final cue = tester.widget<StatusCue>(find.byType(StatusCue));
    expect(cue.semanticLabel, contains('Tap tag 1'));
  });

  testWidgets('only the scanning row is disabled while waiting', (
    tester,
  ) async {
    await tester.pumpWidget(const MaterialApp(home: RoomProofScreen()));
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey<String>('register-1')));
    await tester.pump();

    final busyCue = tester.widget<StatusCue>(find.byType(StatusCue));
    expect(busyCue.resolvedKind, CueKind.busy);

    final other = tester.widget<FilledButton>(
      find.byKey(const ValueKey<String>('register-0')),
    );
    expect(other.onPressed, isNull, reason: 'one scan at a time');
  });

  testWidgets('says so when the device cannot scan, rather than waiting', (
    tester,
  ) async {
    nfcStarts = false;
    await tester.pumpWidget(const MaterialApp(home: RoomProofScreen()));
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey<String>('register-0')));
    await tester.pump();

    final cue = tester.widget<StatusCue>(find.byType(StatusCue));
    expect(cue.semanticLabel, contains('unavailable'));
  });

  testWidgets('each registered tag is shown against its own slot', (
    tester,
  ) async {
    await RoomProofSettings.saveNfcTagAt(0, '04a2b3c4');
    await RoomProofSettings.saveNfcTagAt(1, '04ffee11');
    await tester.pumpWidget(const MaterialApp(home: RoomProofScreen()));
    await tester.pump();
    expect(find.text('04a2b3c4'), findsOneWidget);
    expect(find.text('04ffee11'), findsOneWidget);
    expect(find.byKey(const ValueKey<String>('register-0')), findsOneWidget);
    // Verify key exists; "again" is part of the semantic label in the icon.
    final registerBtn = tester.widget<FilledButton>(
      find.byKey(const ValueKey<String>('register-0')),
    );
    expect(registerBtn.onPressed, isNotNull);
  });

  testWidgets('registered status shows the confirmation message', (
    tester,
  ) async {
    await RoomProofSettings.saveNfcTagAt(0, 'abc');
    await tester.pumpWidget(const MaterialApp(home: RoomProofScreen()));
    await tester.pump();

    final cue = tester.widget<StatusCue>(find.byType(StatusCue));
    expect(cue.semanticLabel, 'Tag 1 registered.');
  });
}
