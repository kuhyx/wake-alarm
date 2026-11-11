import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:wake_alarm_sync/screens/ring_screen.dart';
import 'package:wake_alarm_sync/screens/ring_stakes_line.dart';
import 'package:wake_alarm_sync/services/ring_start_recorder.dart';
import 'package:wake_alarm_sync/ui/cues.dart';

import 'fake_enforcement_channel.dart';

/// Counts calls instead of touching storage or the network.
class _CountingRecorder extends RingStartRecorder {
  int calls = 0;

  @override
  Future<bool> record() async {
    calls++;
    return true;
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late FakeEnforcementChannel native;

  setUp(() {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    native = FakeEnforcementChannel()..install();
  });

  Future<void> pumpLine(WidgetTester tester) async {
    await tester.pumpWidget(
      const MaterialApp(home: Scaffold(body: RingStakesLine())),
    );
    await tester.pump();
  }

  testWidgets('a stick-day ring shows what not dismissing costs', (
    tester,
  ) async {
    native.state = nativeState();
    await pumpLine(tester);
    final cue = tester.widget<SpokenLabel>(find.byType(SpokenLabel));
    const expected =
        'Stick day: no dismiss by 07:15 → apps locked through Fri 2 Oct';
    expect(cue.semanticLabel, expected);
    expect(find.text('07:15'), findsOneWidget);
    expect(find.text('02.10'), findsOneWidget);
  });

  testWidgets('nothing once today was dismissed', (tester) async {
    native.state = nativeState(dismissedToday: true);
    await pumpLine(tester);
    expect(find.byType(Text), findsNothing);
  });

  testWidgets('nothing when the platform answers nothing', (tester) async {
    await pumpLine(tester);
    expect(find.byType(Text), findsNothing);
  });

  testWidgets('nothing, and no crash, with no channel at all', (tester) async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(native.channel, null);
    await pumpLine(tester);
    expect(find.byType(Text), findsNothing);
  });

  testWidgets('opening the ring screen records the ring start once', (
    tester,
  ) async {
    native.state = nativeState();
    final recorder = _CountingRecorder();
    await tester.pumpWidget(MaterialApp(home: RingScreen(ringStart: recorder)));
    await tester.pump();
    expect(recorder.calls, 1);
    expect(find.byType(StatusCue), findsOneWidget);
    // The ring screen's own timers (bypass, step poll) outlive the test.
    await tester.pumpWidget(const SizedBox.shrink());
  });
}
