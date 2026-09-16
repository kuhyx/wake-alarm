import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:wake_alarm_sync/screens/session_screen.dart';
import 'package:wake_alarm_sync/services/alarm_scheduler.dart';
import 'package:wake_alarm_sync/services/morning_session.dart';
import 'package:wake_alarm_sync/services/session_rules.dart';
import 'package:wake_alarm_sync/services/session_store.dart';
import 'package:wake_alarm_sync/services/session_tag_settings.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late List<MethodCall> calls;
  late DateTime now;
  int? idleMs;
  var published = 0;

  void mockChannel() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
          const MethodChannel(AlarmScheduler.channelName),
          (call) async {
            calls.add(call);
            if (call.method == 'hasNfc') return true;
            if (call.method == 'motionIdleMillis') return idleMs ?? -1;
            return null;
          },
        );
  }

  /// Delivers a tag from the platform side, as `NfcReader` does.
  Future<void> tap(String tagId) async {
    const codec = StandardMethodCodec();
    await TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .handlePlatformMessage(
          AlarmScheduler.channelName,
          codec.encodeMethodCall(MethodCall('onNfcTag', tagId)),
          (_) {},
        );
  }

  List<String> methods() => calls.map((c) => c.method).toList();

  Future<void> tick(WidgetTester tester, [int seconds = 1]) async {
    for (var i = 0; i < seconds; i++) {
      await tester.pump(kSessionTick);
    }
    await tester.pump();
  }

  setUp(() async {
    calls = <MethodCall>[];
    now = DateTime(2026, 9, 17, 8, 4);
    idleMs = null;
    published = 0;
    SharedPreferences.setMockInitialValues(<String, Object>{});
    mockChannel();
    await SessionTagSettings.replaceAll(<String>['bath', 'ward', 'desk'], '');
  });

  Future<void> pumpSession(WidgetTester tester) async {
    await tester.pumpWidget(
      MaterialApp(
        routes: <String, WidgetBuilder>{
          '/': (_) => SessionScreen(
            clock: () => now,
            publish: () async {
              published++;
              return 'pushed';
            },
          ),
          '/ring': (_) => const Scaffold(body: Text('RING')),
        },
      ),
    );
    await tester.pump();
    await tester.pump();
  }

  Future<void> logWeight(WidgetTester tester, String kg) async {
    await tester.enterText(find.byType(TextField), kg);
    await tester.tap(find.text('Log weight'));
    await tester.pump();
  }

  testWidgets('starts a session cold and arms the first deadline', (
    tester,
  ) async {
    await pumpSession(tester);
    expect(find.text('Stay up'), findsOneWidget);
    expect(find.text('Weigh in'), findsOneWidget);
    expect(find.text('Alarm returns in 10:00'), findsOneWidget);
    expect(methods(), contains('beginMotionWatch'));
    final arm = calls.firstWhere((c) => c.method == 'armReRing');
    expect(arm.arguments, <String, int?>{
      'atMillis': now.add(MorningSession.legWindow).millisecondsSinceEpoch,
    });
    expect((await SessionStore().loadCurrent())?.date, '2026-09-17');
  });

  testWidgets('walks every leg, then finishes, archives and closes', (
    tester,
  ) async {
    await pumpSession(tester);
    await logWeight(tester, '72,4');
    expect(find.textContaining('now tap the bathroom tag'), findsOneWidget);
    expect(find.byType(TextField), findsNothing);
    await tap('desk');
    await tester.pump();
    expect(find.text('Not the bathroom tag'), findsOneWidget);
    await tap('bath');
    await tester.pump();
    expect(find.text('Weigh in — 72.4 kg'), findsOneWidget);
    expect(find.textContaining('tag counts in 08:00'), findsOneWidget);
    await tap('bath');
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('Too early'), findsOneWidget);
    now = now.add(const Duration(minutes: 9));
    await tick(tester);
    expect(find.textContaining('Alarm returns in'), findsOneWidget);
    await tap('bath');
    await tap('ward');
    await tap('desk');
    await tester.pump();
    await tester.pump();
    expect(methods(), contains('finishSession'));
    expect(methods().last, 'closeRingScreen');
    expect(published, 1);
    final store = SessionStore();
    expect(await store.loadCurrent(), isNull);
    final done = (await store.history()).single;
    expect(done.outcome, SessionOutcome.completed);
    expect(done.weightKg, 72.4);
    expect(done.reRings, 0);
  });

  testWidgets('a still phone rings and routes to the ring screen', (
    tester,
  ) async {
    await pumpSession(tester);
    await logWeight(tester, '72');
    await tap('bath');
    now = now.add(const Duration(minutes: 9));
    await tap('bath');
    await tester.pump();
    idleMs = MorningSession.stillnessLimit.inMilliseconds;
    await tick(tester, kMotionPollEvery);
    await tester.pumpAndSettle();
    expect(methods(), contains('ringNow'));
    expect(find.text('RING'), findsOneWidget);
    final saved = (await SessionStore().loadCurrent())!;
    expect(saved.pendingReRingReason, 'still:dressed');
    expect(saved.currentLeg, SessionLeg.dressed);
  });

  testWidgets('stillness is ignored while showering', (tester) async {
    await pumpSession(tester);
    await logWeight(tester, '72');
    await tap('bath');
    idleMs = MorningSession.stillnessLimit.inMilliseconds * 2;
    await tick(tester, kMotionPollEvery);
    expect(methods(), isNot(contains('ringNow')));
  });

  testWidgets('a missed deadline the alarm did not fire rings from Dart', (
    tester,
  ) async {
    await pumpSession(tester);
    now = now.add(MorningSession.legWindow).add(const Duration(seconds: 30));
    await tick(tester);
    await tester.pumpAndSettle();
    expect(methods(), contains('ringNow'));
    expect(
      (await SessionStore().loadCurrent())!.pendingReRingReason,
      'deadline:bathroomIn',
    );
  });

  testWidgets('resumes a stored session and bypasses a spent leg', (
    tester,
  ) async {
    final started = now.subtract(const Duration(minutes: 16));
    final session = SessionRules.start(
      now: started,
      tags: await SessionTagSettings.load(),
      nfcAvailable: true,
    )..recordReRing(now.subtract(const Duration(minutes: 1)));
    await SessionStore().save(session);
    await pumpSession(tester);
    expect(find.text('Re-rings: 1/3'), findsOneWidget);
    expect(
      calls.firstWhere((c) => c.method == 'armReRing').arguments,
      <String, int?>{'atMillis': null},
    );
    await tick(tester);
    expect(find.textContaining('Skipped'), findsOneWidget);
    expect(find.textContaining('(skipped by the clock)'), findsOneWidget);
  });

  testWidgets('a big jump must be typed twice', (tester) async {
    final store = SessionStore();
    await store.archive(
      SessionRules.start(
        now: now.subtract(const Duration(days: 1)),
        tags: const SessionTagSettings(),
        nfcAvailable: false,
      )..weightKg = 70,
    );
    await pumpSession(tester);
    await logWeight(tester, '75');
    expect(find.textContaining('type it again'), findsOneWidget);
    await logWeight(tester, '75');
    expect(find.textContaining('now tap the bathroom tag'), findsOneWidget);
    expect(find.byType(TextField), findsNothing);
  });

  testWidgets('an unknown tag and bad weights are reported', (tester) async {
    await pumpSession(tester);
    await logWeight(tester, 'x');
    expect(find.textContaining('Enter your weight'), findsOneWidget);
    await logWeight(tester, '1');
    expect(find.textContaining('not a body weight'), findsOneWidget);
    expect(find.byType(TextField), findsOneWidget);
    await tap('mystery');
    await tester.pump();
    expect(find.text('Unknown tag'), findsOneWidget);
  });
}
