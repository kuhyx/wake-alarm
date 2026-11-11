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

/// The session screen reached cold by the launcher redirect, not by a ring.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late List<MethodCall> calls;
  final now = DateTime(2026, 9, 17, 8, 40);

  setUp(() async {
    calls = <MethodCall>[];
    SharedPreferences.setMockInitialValues(<String, Object>{});
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
          const MethodChannel(AlarmScheduler.channelName),
          (call) async {
            calls.add(call);
            return call.method == 'hasNfc' ? true : null;
          },
        );
    await SessionTagSettings.replaceAll(<String>['bath', 'ward', 'desk'], '');
  });

  Future<void> pumpCold(WidgetTester tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: SessionScreen(clock: () => now, publish: () async => 'ok'),
      ),
    );
    await tester.pump();
    await tester.pump();
  }

  testWidgets('resumes the persisted session at its live leg', (tester) async {
    final at = now.subtract(const Duration(minutes: 4));
    final session =
        SessionRules.start(
            now: now.subtract(const Duration(minutes: 5)),
            tags: await SessionTagSettings.load(),
            nfcAvailable: true,
          )
          ..enterCheckIn(72, 3, at)
          ..onTag(SessionTagSlot.bathroom, at);
    await SessionStore().save(session);
    await pumpCold(tester);
    expect(find.text('72.0'), findsOneWidget);
    expect(find.text('3/5'), findsOneWidget);
    expect(find.textContaining('04:00'), findsOneWidget);
    final notice = calls.lastWhere((c) => c.method == 'updateSessionNotice');
    expect((notice.arguments as Map<Object?, Object?>)['label'], '🚿 2/4');
    expect(calls.map((c) => c.method), isNot(contains('closeRingScreen')));
  });

  testWidgets('with today already finished it clears the record and closes', (
    tester,
  ) async {
    final done = SessionRules.start(
      now: now.subtract(const Duration(minutes: 30)),
      tags: const SessionTagSettings(),
      nfcAvailable: false,
    )..enterCheckIn(72, 3, now.subtract(const Duration(minutes: 29)));
    expect(done.outcome, SessionOutcome.completed);
    await SessionStore().archive(done);
    await pumpCold(tester);
    final methods = calls.map((c) => c.method).toList();
    expect(methods, contains('finishSession'));
    expect(methods.last, 'closeRingScreen');
    expect(methods, isNot(contains('updateSessionNotice')));
    expect(await SessionStore().loadCurrent(), isNull);
    expect((await SessionStore().history()).length, 1);
  });
}
