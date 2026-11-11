import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:wake_alarm_sync/screens/session_screen.dart';
import 'package:wake_alarm_sync/services/alarm_scheduler.dart';
import 'package:wake_alarm_sync/services/session_store.dart';
import 'package:wake_alarm_sync/services/session_tag_settings.dart';
import 'package:wake_alarm_sync/ui/cues.dart';

/// The session's status sentence, now spoken only.
String statusOf(WidgetTester tester) =>
    tester.widget<StatusCue>(find.byType(StatusCue)).semanticLabel;

/// The check-in half of the session screen (energy + weight) and the two
/// publishes: split from `session_screen_test.dart` at the 250-line cap.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late DateTime now;
  late List<String> publishes;
  late List<bool> storeHadSession;
  Completer<String>? holdFirst;

  void mockChannel() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
          const MethodChannel(AlarmScheduler.channelName),
          (call) async => call.method == 'hasNfc' ? true : null,
        );
  }

  Future<void> tap(String tagId) async {
    const codec = StandardMethodCodec();
    await TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .handlePlatformMessage(
          AlarmScheduler.channelName,
          codec.encodeMethodCall(MethodCall('onNfcTag', tagId)),
          (_) {},
        );
  }

  setUp(() async {
    now = DateTime(2026, 9, 19, 8, 4);
    publishes = <String>[];
    storeHadSession = <bool>[];
    holdFirst = null;
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
              // What the real publisher stages: is the session on disk yet?
              storeHadSession.add(await SessionStore().loadCurrent() != null);
              final hold = holdFirst;
              if (publishes.isEmpty && hold != null) {
                publishes.add('start (held)');
                return await hold.future;
              }
              publishes.add(publishes.isEmpty ? 'start' : 'finish');
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

  Future<void> submit(WidgetTester tester, String kg) async {
    await tester.enterText(find.byType(TextField), kg);
    await tester.tap(find.byKey(const Key('session-log-weight')));
    await tester.pump();
  }

  testWidgets('the start publish runs after the session is stored', (
    tester,
  ) async {
    await pumpSession(tester);
    expect(publishes, <String>['start']);
    expect(storeHadSession, <bool>[true]);
  });

  testWidgets('no energy tapped: the weight is refused and nothing sticks', (
    tester,
  ) async {
    await pumpSession(tester);
    await submit(tester, '72');
    expect(statusOf(tester), contains('Tap your energy'));
    expect(find.byType(TextField), findsOneWidget);
    expect((await SessionStore().loadCurrent())?.pendingWeightKg, isNull);
  });

  testWidgets('energy then weight records both on the session', (tester) async {
    await pumpSession(tester);
    await tester.tap(find.widgetWithText(ChoiceChip, '5'));
    await tester.pump();
    await submit(tester, '72');
    expect(find.byKey(const ValueKey('session-row-weigh')), findsOneWidget);
    final session = await SessionStore().loadCurrent();
    expect(session?.energy, 5);
    expect(session?.pendingWeightKg, 72);
  });

  testWidgets('an unknown tag and bad weights are reported', (tester) async {
    await pumpSession(tester);
    await tester.tap(find.widgetWithText(ChoiceChip, '3'));
    await tester.pump();
    await submit(tester, 'x');
    expect(statusOf(tester), contains('Enter your weight'));
    await submit(tester, '1');
    expect(statusOf(tester), contains('not a body weight'));
    expect(find.byType(TextField), findsOneWidget);
    await tap('mystery');
    await tester.pump();
    expect(statusOf(tester), 'Unknown tag');
  });

  testWidgets('the finish publish waits for a start publish in flight', (
    tester,
  ) async {
    // No session tags: the check-in is the whole morning, so it finishes
    // seconds after it started, while the start publish may still be out.
    await SessionTagSettings.replaceAll(<String>['', '', ''], '');
    holdFirst = Completer<String>();
    await pumpSession(tester);
    await tester.tap(find.widgetWithText(ChoiceChip, '2'));
    await tester.pump();
    await submit(tester, '72');
    await tester.pump();
    expect(publishes, <String>['start (held)']);
    holdFirst!.complete('late');
    await tester.pump();
    await tester.pump();
    expect(publishes, <String>['start (held)', 'finish']);
  });
}
