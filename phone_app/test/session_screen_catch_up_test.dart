import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:wake_alarm_sync/screens/session_screen.dart';
import 'package:wake_alarm_sync/services/alarm_scheduler.dart';
import 'package:wake_alarm_sync/services/morning_session.dart';
import 'package:wake_alarm_sync/services/session_store.dart';
import 'package:wake_alarm_sync/services/session_tag_settings.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late List<MethodCall> calls;
  late DateTime now;
  var ringing = false;

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

  setUp(() async {
    calls = <MethodCall>[];
    now = DateTime(2026, 9, 17, 8, 4);
    ringing = false;
    SharedPreferences.setMockInitialValues(<String, Object>{});
    mockChannel();
    await SessionTagSettings.replaceAll(<String>['bath', 'ward', 'desk'], '');
  });

  Future<void> pumpSession(WidgetTester tester) async {
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
  }

  /// Taps energy 3 (required since the check-in) and submits [kg].
  Future<void> logWeight(WidgetTester tester, String kg) async {
    await tester.tap(find.widgetWithText(ChoiceChip, '3'));
    await tester.pump();
    await tester.enterText(find.byType(TextField), kg);
    await tester.tap(find.text('Log weight'));
    await tester.pump();
  }

  testWidgets('a forgotten shower tag is caught up by the wardrobe', (
    tester,
  ) async {
    await pumpSession(tester);
    await logWeight(tester, '72');
    await tap('bath');
    await tester.pump();
    now = now.add(const Duration(minutes: 9));
    await tap('ward');
    await tester.pump();
    final saved = (await SessionStore().loadCurrent())!;
    expect(saved.passedHow[SessionLeg.showerDone], LegPass.caughtUp);
    expect(saved.currentLeg, SessionLeg.atDesk);
    final arm = calls.lastWhere((c) => c.method == 'armReRing');
    final deadline = now.add(MorningSession.legWindow).millisecondsSinceEpoch;
    expect(arm.arguments, <String, int?>{'atMillis': deadline});
    expect(methods(), isNot(contains('ringNow')));
  });
}
