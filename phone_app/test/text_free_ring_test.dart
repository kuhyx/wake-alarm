import 'dart:math';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:wake_alarm_sync/screens/ring_screen.dart';
import 'package:wake_alarm_sync/screens/session_screen.dart';
import 'package:wake_alarm_sync/services/alarm_scheduler.dart';
import 'package:wake_alarm_sync/services/challenge.dart';
import 'package:wake_alarm_sync/services/dismiss_gate.dart';
import 'package:wake_alarm_sync/services/room_proof_settings.dart';
import 'package:wake_alarm_sync/services/session_notice.dart';
import 'package:wake_alarm_sync/services/session_rules.dart';
import 'package:wake_alarm_sync/services/session_tag_settings.dart';

import 'text_free_support.dart';

const String _tag1 = '04a2b3c4';
const String _tag2 = '04ffee11';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late List<String> calls;
  var steps = 0;
  var hasNfc = true;
  var elapsed = Duration.zero;

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

  Future<ChallengeGenerator> pumpRing(WidgetTester tester) async {
    await RoomProofSettings.saveNfcTagAt(0, _tag1);
    await RoomProofSettings.saveNfcTagAt(1, _tag2);
    await tester.pumpWidget(
      MaterialApp(
        home: RingScreen(
          generator: ChallengeGenerator(random: Random(1)),
          clock: () => elapsed,
        ),
        routes: <String, WidgetBuilder>{
          kSessionRoute: (_) => const Scaffold(body: Text('SESSION')),
        },
      ),
    );
    await tester.pump();
    return ChallengeGenerator(random: Random(1));
  }

  group('ring screen — no words', () {
    testWidgets('at tag 1 stage', (tester) async {
      phoneView(tester);
      await pumpRing(tester);
      expectNoWords(tester, 'RingScreen-tag1');
    });

    testWidgets('after bypass fires (still walk)', (tester) async {
      phoneView(tester);
      await pumpRing(tester);
      await tester.pump(DismissGate.bypassAfter);
      await tester.pump();
      expectNoWords(tester, 'RingScreen-bypass-walk');
    });

    testWidgets('in bypass with steps reached — challenge stage', (
      tester,
    ) async {
      phoneView(tester);
      await pumpRing(tester);
      await tester.pump(DismissGate.bypassAfter);
      await tester.pump();
      steps = 500;
      elapsed = const Duration(minutes: 6);
      await pollSteps(tester);
      expectNoWords(tester, 'RingScreen-challenge-bypass');
    });

    testWidgets('challenge after tag path — no words', (tester) async {
      phoneView(tester);
      await pumpRing(tester);
      // Simulate tag 1 tap
      await TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .handlePlatformMessage(
            AlarmScheduler.channelName,
            const StandardMethodCodec().encodeMethodCall(
              const MethodCall('onNfcTag', _tag1),
            ),
            (_) {},
          );
      steps = 500;
      elapsed = const Duration(minutes: 3);
      await pollSteps(tester);
      // Tag 2 tap to reach challenges
      await TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .handlePlatformMessage(
            AlarmScheduler.channelName,
            const StandardMethodCodec().encodeMethodCall(
              const MethodCall('onNfcTag', _tag2),
            ),
            (_) {},
          );
      await tester.pump();
      expectNoWords(tester, 'RingScreen-challenge-tags');
    });

    testWidgets('all four ChallengeKind variants via different seeds', (
      tester,
    ) async {
      phoneView(tester);
      for (final seed in [1, 2, 3, 4]) {
        await RoomProofSettings.saveNfcTagAt(0, _tag1);
        await RoomProofSettings.saveNfcTagAt(1, _tag2);
        await tester.pumpWidget(
          MaterialApp(
            home: RingScreen(
              generator: ChallengeGenerator(random: Random(seed)),
              clock: () => elapsed,
            ),
            routes: <String, WidgetBuilder>{
              kSessionRoute: (_) => const Scaffold(body: Text('SESSION')),
            },
          ),
        );
        await tester.pump();
        await tester.pump(DismissGate.bypassAfter);
        await tester.pump();
        steps = 500;
        elapsed = const Duration(minutes: 6);
        await pollSteps(tester);
        expectNoWords(tester, 'RingScreen-seed-$seed');
      }
    });
  });

  group('session screen — no words', () {
    testWidgets('right after session starts', (tester) async {
      phoneView(tester);
      late List<MethodCall> calls;
      late DateTime now;
      void mockChannelFn() {
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
            .setMockMethodCallHandler(
              const MethodChannel(AlarmScheduler.channelName),
              (call) async {
                calls.add(call);
                if (call.method == 'hasNfc') return true;
                return null;
              },
            );
      }

      calls = <MethodCall>[];
      now = DateTime(2026, 9, 17, 8, 4);
      SharedPreferences.setMockInitialValues(<String, Object>{});
      mockChannelFn();
      await SessionTagSettings.replaceAll(<String>['bath', 'ward', 'desk'], '');

      await tester.pumpWidget(
        MaterialApp(
          routes: <String, WidgetBuilder>{
            '/': (_) =>
                SessionScreen(clock: () => now, publish: () async => 'pushed'),
            '/ring': (_) => const Scaffold(body: Text('RING')),
          },
        ),
      );
      await tester.pump();
      await tester.pump();
      expectNoWords(tester, 'SessionScreen-start');
    });
  });

  group('notification line', () {
    test('noticeLabel for an active session has no L words', () {
      final session = SessionRules.start(
        now: DateTime(2026, 9, 1, 8),
        tags: const SessionTagSettings(),
        nfcAvailable: false,
      );
      final label = noticeLabel(session);
      final wordRegex = RegExp(r'\p{L}{2,}', unicode: true);
      final words = wordRegex
          .allMatches(label)
          .map((m) => m.group(0)!)
          .toList();
      expect(words, isEmpty, reason: 'noticeLabel had words: $words');
    });
  });
}
