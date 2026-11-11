import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:wake_alarm_sync/main.dart';
import 'package:wake_alarm_sync/screens/ring_screen.dart';
import 'package:wake_alarm_sync/services/alarm_scheduler.dart';
import 'package:wake_alarm_sync/services/challenge.dart';
import 'package:wake_alarm_sync/services/dismiss_gate.dart';
import 'package:wake_alarm_sync/services/room_proof_settings.dart';
import 'package:wake_alarm_sync/ui/cues.dart';

const String _tag1 = '04a2b3c4';
const String _tag2 = '04ffee11';

/// The ring's status sentence, now spoken only (StatusCue.semanticLabel).
String statusOf(WidgetTester tester) =>
    tester.widget<StatusCue>(find.byType(StatusCue)).semanticLabel;

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

  /// Pushes a tag up from Kotlin exactly as `NfcReader` does.
  Future<void> tapTag(WidgetTester tester, String id) async {
    await TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .handlePlatformMessage(
          AlarmScheduler.channelName,
          const StandardMethodCodec().encodeMethodCall(
            MethodCall('onNfcTag', id),
          ),
          (_) {},
        );
    await tester.pump();
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
        routes: <String, WidgetBuilder>{
          kSessionRoute: (_) => const Scaffold(body: Text('SESSION')),
        },
      ),
    );
    await tester.pump();
    return ChallengeGenerator(random: Random(1));
  }

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

  testWidgets('it opens on the checklist, not the challenge', (tester) async {
    await pumpRing(tester);
    expect(find.text('Wake up'), findsNothing);
    expect(find.byKey(const ValueKey<String>('ring-row-tag1')), findsOneWidget);
    expect(
      find.byKey(const ValueKey<String>('ring-row-steps')),
      findsOneWidget,
    );
    expect(find.byKey(const ValueKey<String>('ring-row-tag2')), findsOneWidget);
    expect(find.byKey(const Key('ring-submit')), findsNothing);
  });

  testWidgets('tag 2 tapped first does nothing; tag 1 then works', (
    tester,
  ) async {
    await pumpRing(tester);
    await tapTag(tester, _tag2);
    expect(statusOf(tester), contains('Not tag 1'));

    await tapTag(tester, _tag1);
    expect(statusOf(tester), contains('Tag 1 matched'));
  });

  testWidgets('an unknown tag does not un-latch a passed stage', (
    tester,
  ) async {
    // The regression this change exists to prevent: the old gate assigned the
    // room-proof result straight onto a bool, so a wrong tap after passing
    // sent the user back to the start.
    await pumpRing(tester);
    await tapTag(tester, _tag1);
    await tapTag(tester, 'deadbeef');
    // Still past tag 1: the steps row is live, not the tag 1 row.
    steps = 500;
    elapsed = const Duration(minutes: 3);
    await pollSteps(tester);
    expect(find.byKey(const ValueKey<String>('ring-row-tag2')), findsOneWidget);
  });

  testWidgets('steps do not count before tag 1', (tester) async {
    await pumpRing(tester);
    steps = 500;
    elapsed = const Duration(minutes: 3);
    await pollSteps(tester);
    // Still on tag 1 — walking first must not skip the first location.
    expect(find.byKey(const Key('ring-submit')), findsNothing);
    await tapTag(tester, _tag2);
    expect(statusOf(tester), contains('Not tag 1'));
  });

  testWidgets('after tag 1 the banked steps pass the walk at once', (
    tester,
  ) async {
    // No elapsed-time floor on the normal path (2026-09-16): tag 1 already
    // proved the walk, and the floor was two minutes of ringing that nothing
    // the user did could shorten. It still applies under bypass -- see
    // ring_bypass_test.
    await pumpRing(tester);
    await tapTag(tester, _tag1);
    steps = 500;
    elapsed = const Duration(seconds: 5);
    await pollSteps(tester);
    expect(statusOf(tester), isNot(contains('Keep moving')));
    expect(statusOf(tester), contains('Walked far enough'));
    expect(find.byKey(const ValueKey<String>('ring-row-tag2')), findsOneWidget);
  });

  testWidgets('the full sequence dismisses: tag 1, walk, tag 2, 3 answers', (
    tester,
  ) async {
    final expected = await pumpRing(tester);

    await tapTag(tester, _tag1);
    steps = 500;
    elapsed = const Duration(minutes: 3);
    await pollSteps(tester);
    await tapTag(tester, _tag2);

    expect(find.text('1/3'), findsOneWidget);
    for (var i = 1; i <= DismissGate.challengesNormal; i++) {
      expect(find.text('$i/3'), findsOneWidget);
      await tester.enterText(find.byType(TextField), expected.next().answer);
      await tester.tap(find.byKey(const Key('ring-submit')));
      await tester.pump();
    }

    // The ring stops, then the morning session takes the screen over (see
    // ring_session_handoff_test for the handoff and the away-from-home
    // close). Back is disabled in both halves, so the dismiss must always
    // lead *somewhere*.
    expect(calls, contains('dismiss'));
    await tester.pumpAndSettle();
    expect(find.text('SESSION'), findsOneWidget);
  });

  testWidgets('a wrong answer costs the attempt but not the tally', (
    tester,
  ) async {
    final expected = await pumpRing(tester);
    await tapTag(tester, _tag1);
    steps = 500;
    elapsed = const Duration(minutes: 3);
    await pollSteps(tester);
    await tapTag(tester, _tag2);

    await tester.enterText(find.byType(TextField), expected.next().answer);
    await tester.tap(find.byKey(const Key('ring-submit')));
    await tester.pump();
    expect(find.text('2/3'), findsOneWidget);
    expected.next(); // the screen regenerated after the correct answer

    await tester.enterText(find.byType(TextField), 'definitely wrong');
    await tester.tap(find.byKey(const Key('ring-submit')));
    await tester.pump();
    expect(
      find.text('2/3'),
      findsOneWidget,
      reason: 'cumulative: a wrong answer must not reset the count',
    );
    expect(calls, isNot(contains('closeRingScreen')));
  });
}

/// Local helper so the test need not import dart:async for one call.
void unawaited(Future<void> future) {}
