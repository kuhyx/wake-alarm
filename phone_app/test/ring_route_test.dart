import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:wake_alarm_sync/main.dart';
import 'package:wake_alarm_sync/screens/ring_screen.dart';
import 'package:wake_alarm_sync/services/alarm_scheduler.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    const channel = MethodChannel(AlarmScheduler.channelName);
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
          if (call.method == 'stepCount') return 0;
          if (call.method == 'hasNfc') return false;
          return null;
        });
  });

  testWidgets('the /ring route resolves to the ring screen', (tester) async {
    // AlarmActivity hands "/ring" to the engine as its initial route; if the
    // app does not resolve it the full-screen intent opens the home screen and
    // there is no dismiss path at all.
    await tester.pumpWidget(const WakeAlarmSyncApp());
    final state = tester.state<NavigatorState>(find.byType(Navigator));
    unawaited(state.pushNamed(kRingRoute));
    await tester.pumpAndSettle();

    expect(find.byType(RingScreen), findsOneWidget);
  });

  testWidgets('the ring screen shows the room gate before the challenge', (
    tester,
  ) async {
    await tester.pumpWidget(const MaterialApp(home: RingScreen()));
    await tester.pumpAndSettle();

    expect(find.text('Wake up'), findsOneWidget);
    expect(find.text('Check steps'), findsOneWidget);
    // The challenge must not be reachable until the room proof is satisfied.
    expect(find.text('Dismiss'), findsNothing);
  });

  testWidgets('satisfying the room proof reveals the challenge', (
    tester,
  ) async {
    const channel = MethodChannel(AlarmScheduler.channelName);
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
          if (call.method == 'stepCount') return 500;
          if (call.method == 'hasNfc') return false;
          return null;
        });

    await tester.pumpWidget(const MaterialApp(home: RingScreen()));
    await tester.pumpAndSettle();
    // The stopwatch starts at zero, so steps alone must not be enough yet.
    await tester.tap(find.text('Check steps'));
    await tester.pumpAndSettle();

    expect(find.text('Dismiss'), findsNothing);
    expect(find.textContaining('Keep moving'), findsOneWidget);
  });
}

/// Local helper so the test need not import dart:async for one call.
void unawaited(Future<void> future) {}
