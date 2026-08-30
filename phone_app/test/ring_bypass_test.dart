import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:wake_alarm_sync/screens/ring_screen.dart';
import 'package:wake_alarm_sync/services/alarm_scheduler.dart';
import 'package:wake_alarm_sync/services/challenge.dart';
import 'package:wake_alarm_sync/services/dismiss_gate.dart';
import 'package:wake_alarm_sync/services/room_proof_settings.dart';

const String _tag1 = '04a2b3c4';
const String _tag2 = '04ffee11';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late List<String> calls;
  var steps = 0;
  var hasNfc = true;
  var elapsed = Duration.zero;

  /// Installs the platform mock. Call after changing [steps] / [hasNfc].
  void mockChannel() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
          const MethodChannel(AlarmScheduler.channelName),
          (call) async {
            calls.add(call.method);
            if (call.method == 'stepCount') return steps;
            if (call.method == 'hasNfc') return hasNfc;
            return null;
          },
        );
  }

  /// Lets the periodic step poll run once.
  Future<void> pollSteps(WidgetTester tester) async {
    await tester.pump(kStepPollInterval);
    await tester.pump();
  }

  setUp(() {
    calls = <String>[];
    steps = 0;
    hasNfc = true;
    elapsed = Duration.zero;
    SharedPreferences.setMockInitialValues(<String, Object>{});
    mockChannel();
  });

  /// A ring screen with both tags registered and a controllable clock.
  Future<ChallengeGenerator> pumpRing(WidgetTester tester) async {
    await RoomProofSettings.saveNfcTagAt(0, _tag1);
    await RoomProofSettings.saveNfcTagAt(1, _tag2);
    await tester.pumpWidget(
      MaterialApp(
        home: RingScreen(
          generator: ChallengeGenerator(random: Random(1)),
          clock: () => elapsed,
        ),
      ),
    );
    await tester.pump();
    return ChallengeGenerator(random: Random(1));
  }

  testWidgets('it is not offered before the timer elapses', (tester) async {
    await pumpRing(tester);
    await tester.pump(DismissGate.bypassAfter - const Duration(seconds: 1));
    expect(find.textContaining('Tags unavailable'), findsNothing);
    expect(find.text('Tap tag 1'), findsOneWidget);
  });

  testWidgets('after the timer it skips the tags but still needs the walk', (
    tester,
  ) async {
    await pumpRing(tester);
    await tester.pump(DismissGate.bypassAfter);
    await tester.pump();

    expect(find.textContaining('Tags unavailable'), findsOneWidget);
    expect(find.text('Tap tag 1'), findsNothing);
    expect(find.text('Walk 25 steps'), findsOneWidget);
    expect(find.text('Submit'), findsNothing);

    steps = 500;
    elapsed = const Duration(minutes: 6);
    await pollSteps(tester);
    expect(find.text('Question 1 of 6'), findsOneWidget);
  });

  testWidgets('an unregistered second tag bypasses immediately', (
    tester,
  ) async {
    await RoomProofSettings.saveNfcTagAt(0, _tag1);
    await tester.pumpWidget(
      MaterialApp(home: RingScreen(clock: () => elapsed)),
    );
    await tester.pump();
    expect(find.textContaining('Register two NFC tags'), findsOneWidget);
    expect(find.textContaining('Tags unavailable'), findsOneWidget);
  });

  testWidgets('no NFC hardware bypasses immediately', (tester) async {
    hasNfc = false;
    mockChannel();
    await pumpRing(tester);
    expect(find.textContaining('NFC is off'), findsOneWidget);
    expect(find.text('Tap tag 1'), findsNothing);
  });
}

/// Local helper so the test need not import dart:async for one call.
void unawaited(Future<void> future) {}
