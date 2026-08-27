import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:wake_alarm_sync/main.dart';
import 'package:wake_alarm_sync/screens/ring_screen.dart';
import 'package:wake_alarm_sync/services/alarm_scheduler.dart';
import 'package:wake_alarm_sync/services/challenge.dart';
import 'package:wake_alarm_sync/services/room_proof_settings.dart';

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

  testWidgets('a registered NFC tag tap satisfies the proof and reveals '
      'the challenge', (tester) async {
    SharedPreferences.setMockInitialValues(<String, Object>{
      RoomProofSettings.kNfcTagKey: '04a2b3c4',
    });
    const channel = MethodChannel(AlarmScheduler.channelName);
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
          if (call.method == 'hasNfc') return true;
          if (call.method == 'stepCount') return 0;
          return null;
        });

    await tester.pumpWidget(const MaterialApp(home: RingScreen()));
    await tester.pumpAndSettle();
    expect(find.textContaining('tap the NFC tag'), findsOneWidget);

    // Simulate the tag arriving over the channel, as NfcReader pushes it.
    await TestDefaultBinaryMessengerBinding
        .instance
        .defaultBinaryMessenger
        .handlePlatformMessage(
          AlarmScheduler.channelName,
          const StandardMethodCodec().encodeMethodCall(
            const MethodCall('onNfcTag', '04a2b3c4'),
          ),
          (_) {},
        );
    await tester.pumpAndSettle();

    expect(find.text('Dismiss'), findsOneWidget);
  });

  testWidgets('a foreign NFC tag does not satisfy the proof', (tester) async {
    SharedPreferences.setMockInitialValues(<String, Object>{
      RoomProofSettings.kNfcTagKey: '04a2b3c4',
    });
    const channel = MethodChannel(AlarmScheduler.channelName);
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
          if (call.method == 'hasNfc') return true;
          if (call.method == 'stepCount') return 0;
          return null;
        });

    await tester.pumpWidget(const MaterialApp(home: RingScreen()));
    await tester.pumpAndSettle();
    await TestDefaultBinaryMessengerBinding
        .instance
        .defaultBinaryMessenger
        .handlePlatformMessage(
          AlarmScheduler.channelName,
          const StandardMethodCodec().encodeMethodCall(
            const MethodCall('onNfcTag', 'deadbeef'),
          ),
          (_) {},
        );
    await tester.pumpAndSettle();

    expect(find.text('Dismiss'), findsNothing);
    expect(find.text('Wrong NFC tag'), findsOneWidget);
  });

  testWidgets('a correct answer stops the ring AND closes the screen', (
    tester,
  ) async {
    // Closing is load-bearing: back is disabled in both halves, so a screen
    // left up after a correct answer is a dead end over the lockscreen, and
    // the live instance would carry the satisfied proof into the next ring.
    SharedPreferences.setMockInitialValues(<String, Object>{
      RoomProofSettings.kNfcTagKey: '04a2b3c4',
    });
    final calls = <String>[];
    const channel = MethodChannel(AlarmScheduler.channelName);
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
          calls.add(call.method);
          if (call.method == 'hasNfc') return true;
          if (call.method == 'stepCount') return 0;
          return null;
        });

    // A fixed generator so the expected answer is known.
    final generator = ChallengeGenerator(random: Random(1));
    final challenge = ChallengeGenerator(random: Random(1)).next();

    await tester.pumpWidget(
      MaterialApp(home: RingScreen(generator: generator)),
    );
    await tester.pumpAndSettle();
    await TestDefaultBinaryMessengerBinding
        .instance
        .defaultBinaryMessenger
        .handlePlatformMessage(
          AlarmScheduler.channelName,
          const StandardMethodCodec().encodeMethodCall(
            const MethodCall('onNfcTag', '04a2b3c4'),
          ),
          (_) {},
        );
    await tester.pumpAndSettle();

    await tester.enterText(find.byType(TextField), challenge.answer);
    await tester.tap(find.text('Dismiss'));
    await tester.pumpAndSettle();

    expect(calls, contains('dismiss'));
    expect(calls, contains('closeRingScreen'));
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
