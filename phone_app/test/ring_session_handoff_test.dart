import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:wake_alarm_sync/screens/ring_screen.dart';
import 'package:wake_alarm_sync/screens/session_screen.dart';
import 'package:wake_alarm_sync/services/alarm_policy.dart';
import 'package:wake_alarm_sync/services/alarm_ramp.dart';
import 'package:wake_alarm_sync/services/alarm_scheduler.dart';
import 'package:wake_alarm_sync/services/challenge.dart';
import 'package:wake_alarm_sync/services/home_location_settings.dart';
import 'package:wake_alarm_sync/services/ramp_progress.dart';
import 'package:wake_alarm_sync/services/room_proof_settings.dart';
import 'package:wake_alarm_sync/services/session_store.dart';
import 'package:wake_alarm_sync/services/session_tag_settings.dart';

const String _tag1 = '04a2b3c4';
const String _tag2 = '04ffee11';

/// The dismiss no longer ends the morning: it hands over to the session,
/// inside the same activity, and the session must hear the tags.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late List<String> calls;
  late List<Object?> armed;
  Map<String, Object?>? presence;

  setUp(() async {
    calls = <String>[];
    armed = <Object?>[];
    presence = null;
    SharedPreferences.setMockInitialValues(<String, Object>{});
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
          const MethodChannel(AlarmScheduler.channelName),
          (call) async {
            calls.add(call.method);
            if (call.method == 'armSchedule') armed.add(call.arguments);
            if (call.method == 'stepCount') return 500;
            if (call.method == 'hasNfc') return true;
            if (call.method == 'readPresence') return presence;
            return null;
          },
        );
    await RoomProofSettings.saveNfcTagAt(0, _tag1);
    await RoomProofSettings.saveNfcTagAt(1, _tag2);
    await SessionTagSettings.saveTagAt(SessionTagSlot.bathroom, 'bath');
  });

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

  /// Pumps the ring inside an app that also knows the session route, with
  /// each screen building its own scheduler exactly as production does.
  Future<ChallengeGenerator> pumpApp(WidgetTester tester) async {
    await tester.pumpWidget(
      MaterialApp(
        routes: <String, WidgetBuilder>{
          '/': (_) => RingScreen(
            generator: ChallengeGenerator(random: Random(1)),
            clock: () => const Duration(minutes: 3),
          ),
          kSessionRoute: (_) => SessionScreen(publish: () async => 'ok'),
        },
      ),
    );
    await tester.pump();
    return ChallengeGenerator(random: Random(1));
  }

  /// Tag 1, the walk, tag 2, three answers.
  Future<void> dismiss(WidgetTester tester, ChallengeGenerator answers) async {
    await tapTag(tester, _tag1);
    await tester.pump(kStepPollInterval);
    await tester.pump();
    await tapTag(tester, _tag2);
    for (var i = 0; i < 3; i++) {
      await tester.enterText(find.byType(TextField), answers.next().answer);
      await tester.tap(find.text('Submit'));
      await tester.pump();
    }
    await tester.pumpAndSettle();
  }

  testWidgets('the dismiss opens the session instead of closing', (
    tester,
  ) async {
    final answers = await pumpApp(tester);
    await dismiss(tester, answers);
    expect(find.byType(SessionScreen), findsOneWidget);
    expect(find.byType(RingScreen), findsNothing);
    expect(calls, contains('dismiss'));
    expect(calls, isNot(contains('closeRingScreen')));
    expect((await SessionStore().loadCurrent())?.reRings, 0);
  });

  testWidgets('the dismiss re-arms the ramp, not the spent override', (
    tester,
  ) async {
    // dismiss() natively re-arms the *stored* time, which is the one-shot
    // override just spent; without an explicit re-arm it rang at 05:00 every
    // day until the home screen was next opened.
    await AlarmPolicy.setEarlier(5, 0);
    final answers = await pumpApp(tester);
    await dismiss(tester, answers);
    final next = AlarmPolicy.resolve(DateTime.now(), null);
    expect(
      calls.lastIndexOf('armSchedule'),
      greaterThan(calls.indexOf('dismiss')),
    );
    expect(armed.last, <String, int>{'hour': next.hour, 'minute': next.minute});
    expect(next.isOverridden, isFalse);
    // The dismiss earned today's minute -- unless today is a workday.
    final now = DateTime.now();
    expect(
      (await RampProgress.load()).contains(rampDateKey(now)),
      !isWorkday(now),
    );
  });

  testWidgets('the session hears tags after the ring screen is gone', (
    tester,
  ) async {
    // The ring screen's dispose runs *after* the session screen's initState,
    // and used to wipe the listener the session had just registered: the
    // Pixel showed a session that never heard a single tag (2026-09-16).
    final answers = await pumpApp(tester);
    await dismiss(tester, answers);
    await tester.tap(find.widgetWithText(ChoiceChip, '4'));
    await tester.pump();
    await tester.enterText(find.byType(TextField), '72');
    await tester.tap(find.text('Log weight'));
    await tester.pump();
    await tapTag(tester, 'bath');
    await tester.pump();
    expect(find.text('Weigh in — 72.0 kg · energy 4/5'), findsOneWidget);
    expect(find.textContaining('tag counts in'), findsOneWidget);
  });

  testWidgets('away from home the dismiss still just closes', (tester) async {
    await HomeLocationSettings.capture(ssid: 'Orange_Home');
    presence = <String, Object?>{'ssid': 'Hotel_Guest', 'reason': 'ok'};
    final answers = await pumpApp(tester);
    await tester.pump();
    // Away: tags skipped, so the walk and three answers are the whole gate.
    await tester.pump(kStepPollInterval);
    await tester.pump();
    for (var i = 0; i < 3; i++) {
      await tester.enterText(find.byType(TextField), answers.next().answer);
      await tester.tap(find.text('Submit'));
      await tester.pump();
    }
    await tester.pumpAndSettle();
    expect(calls.last, 'closeRingScreen');
    expect(find.byType(SessionScreen), findsNothing);
    expect(await SessionStore().loadCurrent(), isNull);
  });
}
