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
import 'package:wake_alarm_sync/ui/cues.dart';

/// The session's status sentence, now spoken only.
String statusOf(WidgetTester tester) =>
    tester.widget<StatusCue>(find.byType(StatusCue)).semanticLabel;

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late List<MethodCall> calls;
  late DateTime now;
  var ringing = false;
  var published = 0;

  void mockChannel() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
          const MethodChannel(AlarmScheduler.channelName),
          (call) async {
            calls.add(call);
            if (call.method == 'hasNfc') return true;
            if (call.method == 'isRinging') return ringing;
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
    ringing = false;
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

  /// Taps energy 3 (required since the check-in) and submits [kg].
  Future<void> logWeight(WidgetTester tester, String kg) async {
    await tester.tap(find.widgetWithText(ChoiceChip, '3'));
    await tester.pump();
    await tester.enterText(find.byType(TextField), kg);
    await tester.tap(find.byKey(const Key('session-log-weight')));
    await tester.pump();
  }

  testWidgets('starts a session cold and arms the first deadline', (
    tester,
  ) async {
    await pumpSession(tester);
    expect(find.byKey(const ValueKey('session-row-weigh')), findsOneWidget);
    final deadline = now.add(MorningSession.legWindow).millisecondsSinceEpoch;
    final arm = calls.firstWhere((c) => c.method == 'armReRing');
    expect(arm.arguments, <String, int?>{'atMillis': deadline});
    // The launcher-redirect record follows the deadline in the same breath.
    final notice = calls.firstWhere((c) => c.method == 'updateSessionNotice');
    expect(notice.arguments, <String, Object?>{
      'date': '2026-09-17',
      'label': '🛁 1/4',
      'deadlineMillis': deadline,
    });
    expect((await SessionStore().loadCurrent())?.date, '2026-09-17');
  });

  testWidgets('every leg change re-points the native notice', (tester) async {
    await pumpSession(tester);
    await logWeight(tester, '72');
    await tap('bath');
    await tester.pump();
    final labels = calls
        .where((c) => c.method == 'updateSessionNotice')
        .map((c) => (c.arguments as Map<Object?, Object?>)['label'])
        .toList();
    expect(labels.last, '🚿 2/4');
    expect(methods(), isNot(contains('beginMotionWatch')));
  });

  testWidgets('walks every leg, then finishes, archives and closes', (
    tester,
  ) async {
    await pumpSession(tester);
    await logWeight(tester, '72,4');
    expect(find.byKey(const ValueKey('session-row-weigh')), findsOneWidget);
    expect(find.byType(TextField), findsNothing);
    await tap('desk');
    await tester.pump();
    expect(statusOf(tester), 'Not the bathroom tag');
    await tap('bath');
    await tester.pump();
    expect(find.text('72.4'), findsOneWidget);
    expect(find.text('3/5'), findsOneWidget);
    await tap('bath');
    await tester.pump();
    await tester.pump();
    expect(statusOf(tester), startsWith('Too early'));
    now = now.add(const Duration(minutes: 9));
    await tick(tester);
    expect(find.text('09:00'), findsOneWidget);
    for (final id in <String>['bath', 'ward', 'desk']) {
      await tap(id);
    }
    await tester.pump();
    await tester.pump();
    expect(methods(), contains('finishSession'));
    expect(methods().last, 'closeRingScreen');
    expect(published, 2); // once at start, once at finish
    final store = SessionStore();
    expect(await store.loadCurrent(), isNull);
    final done = (await store.history()).single;
    expect(done.outcome, SessionOutcome.completed);
    expect(done.weightKg, 72.4);
    expect(done.reRings, 0);
  });

  testWidgets('a native ring already sounding routes to the ring screen', (
    tester,
  ) async {
    await pumpSession(tester);
    await logWeight(tester, '72');
    await tap('bath');
    now = now.add(const Duration(minutes: 9));
    await tap('bath');
    await tester.pump();
    ringing = true;
    await tick(tester);
    await tester.pumpAndSettle();
    expect(methods(), contains('ringNow'));
    expect(find.text('RING'), findsOneWidget);
    final saved = (await SessionStore().loadCurrent())!;
    expect(saved.pendingReRingReason, 'deadline:dressed');
    expect(saved.currentLeg, SessionLeg.dressed);
  });

  testWidgets('a silent phone keeps ticking without ringing', (tester) async {
    await pumpSession(tester);
    await logWeight(tester, '72');
    await tap('bath');
    await tick(tester, 5);
    expect(methods(), contains('isRinging'));
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
    expect(find.text('1/3'), findsOneWidget);
    expect(
      calls.firstWhere((c) => c.method == 'armReRing').arguments,
      <String, int?>{'atMillis': null},
    );
    await tick(tester);
    expect(
      find.byKey(const ValueKey('session-row-bathroomIn')),
      findsOneWidget,
    );
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
    expect(statusOf(tester), contains('type it again'));
    await logWeight(tester, '75');
    expect(statusOf(tester), contains('now tap the bathroom tag within 2 min'));
    expect(find.byType(TextField), findsNothing);
  });
}
