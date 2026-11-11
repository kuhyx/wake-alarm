import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:wake_alarm_sync/screens/ring_screen.dart';
import 'package:wake_alarm_sync/services/alarm_scheduler.dart';
import 'package:wake_alarm_sync/services/challenge.dart';
import 'package:wake_alarm_sync/services/dismiss_gate.dart';
import 'package:wake_alarm_sync/services/home_location_settings.dart';
import 'package:wake_alarm_sync/services/room_proof_settings.dart';
import 'package:wake_alarm_sync/ui/cues.dart';

const String _tag1 = '04a2b3c4';
const String _tag2 = '04ffee11';

/// The ring's status sentence, now spoken only (StatusCue.semanticLabel).
String statusOf(WidgetTester tester) =>
    tester.widget<StatusCue>(find.byType(StatusCue)).semanticLabel;

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  var steps = 0;
  var elapsed = Duration.zero;
  Map<String, Object?>? presence;

  void mockChannel() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
          const MethodChannel(AlarmScheduler.channelName),
          (call) async {
            if (call.method == 'stepCount') return steps;
            if (call.method == 'hasNfc') return true;
            if (call.method == 'readPresence') return presence;
            return null;
          },
        );
  }

  setUp(() {
    steps = 0;
    elapsed = Duration.zero;
    presence = null;
    SharedPreferences.setMockInitialValues(<String, Object>{});
    mockChannel();
  });

  /// A ring screen with both tags registered and a controllable clock.
  Future<void> pumpRing(WidgetTester tester) async {
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
    await tester.pump();
  }

  testWidgets('at home the strict sequence is unchanged', (tester) async {
    await HomeLocationSettings.capture(ssid: 'Orange_Home');
    presence = <String, Object?>{'ssid': 'Orange_Home', 'reason': 'ok'};
    await pumpRing(tester);

    expect(find.byKey(const ValueKey<String>('ring-row-tag1')), findsOneWidget);
    expect(find.byKey(const ValueKey<String>('ring-row-tag2')), findsOneWidget);
  });

  testWidgets('away it skips the tags, keeps the walk, and asks 3', (
    tester,
  ) async {
    await HomeLocationSettings.capture(ssid: 'Orange_Home');
    presence = <String, Object?>{'ssid': 'Hotel_Guest', 'reason': 'ok'};
    await pumpRing(tester);

    expect(find.byKey(const Key('ring-bypass')), findsWidgets);
    // The persistent line, not the status that the step poll overwrites.
    expect(statusOf(tester), contains('Away from home'));
    expect(statusOf(tester), isNot(contains('Tags unavailable')));
    expect(find.text('Tap tag 1'), findsNothing);
    expect(find.text('Tap tag 2'), findsNothing);
    // The walk is never skipped: away is where the tags are, not the bed.
    expect(
      find.byKey(const ValueKey<String>('ring-row-steps')),
      findsOneWidget,
    );

    steps = 500;
    elapsed = const Duration(minutes: 3);
    await tester.pump(kStepPollInterval);
    await tester.pump();
    expect(find.text('1/3'), findsOneWidget);
  });

  testWidgets('the five-minute timer does not bump an away morning to 6', (
    tester,
  ) async {
    await HomeLocationSettings.capture(ssid: 'Orange_Home');
    presence = <String, Object?>{'ssid': 'Hotel_Guest', 'reason': 'ok'};
    await pumpRing(tester);

    steps = 500;
    elapsed = const Duration(minutes: 3);
    await tester.pump(kStepPollInterval);
    await tester.pump();
    expect(find.text('1/3'), findsOneWidget);

    // An away morning routinely outlasts the bypass timer.
    await tester.pump(DismissGate.bypassAfter);
    await tester.pump();
    expect(find.text('1/3'), findsOneWidget);
    expect(find.text('1/6'), findsNothing);
  });

  testWidgets('unreadable presence is away, per the chosen fail mode', (
    tester,
  ) async {
    await HomeLocationSettings.capture(ssid: 'Orange_Home');
    presence = <String, Object?>{'reason': 'no-permission'};
    await pumpRing(tester);

    expect(statusOf(tester), contains('location permission denied'));
    expect(find.text('Tap tag 1'), findsNothing);
  });

  testWidgets('away wins over missing tags, so the count stays 3', (
    tester,
  ) async {
    // Ordering regression: if the missing-tag bypass were applied first it
    // would latch 6, and the away verdict arriving later could not lower it.
    await HomeLocationSettings.capture(ssid: 'Orange_Home');
    presence = <String, Object?>{'ssid': 'Hotel_Guest', 'reason': 'ok'};
    await RoomProofSettings.saveNfcTagAt(0, _tag1);
    await tester.pumpWidget(
      MaterialApp(home: RingScreen(clock: () => elapsed)),
    );
    await tester.pump();
    await tester.pump();

    steps = 500;
    elapsed = const Duration(minutes: 3);
    await tester.pump(kStepPollInterval);
    await tester.pump();
    expect(find.text('1/3'), findsOneWidget);
  });
}
