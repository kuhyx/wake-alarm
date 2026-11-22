import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:wake_alarm_sync/screens/session_screen.dart';
import 'package:wake_alarm_sync/services/alarm_scheduler.dart';
import 'package:wake_alarm_sync/services/session_store.dart';
import 'package:wake_alarm_sync/services/session_tag_settings.dart';

/// A bypass during a live session restarts the ring natively; the session
/// screen finds it sounding and must name the re-ring for the bypass, not
/// for the leg's deadline (C7's emulator run recorded `deadline:bathroomIn`).
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  final now = DateTime(2026, 9, 17, 8, 4);
  String? bypassCause;
  late List<String> calls;

  setUp(() async {
    calls = <String>[];
    bypassCause = null;
    SharedPreferences.setMockInitialValues(<String, Object>{});
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
          const MethodChannel(AlarmScheduler.channelName),
          (call) async {
            calls.add(call.method);
            if (call.method == 'hasNfc') return true;
            if (call.method == 'isRinging') return true;
            if (call.method == 'takeBypassReRing') return bypassCause;
            return null;
          },
        );
    await SessionTagSettings.replaceAll(<String>['bath', 'ward', 'desk'], '');
  });

  Future<String?> ringReasonAfterOneTick(WidgetTester tester) async {
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
    await tester.pump(kSessionTick);
    await tester.pumpAndSettle();
    expect(find.text('RING'), findsOneWidget);
    return (await SessionStore().loadCurrent())!.pendingReRingReason;
  }

  testWidgets('a ring a bypass started is named for the bypass', (
    tester,
  ) async {
    bypassCause = 'suspended';
    expect(await ringReasonAfterOneTick(tester), 'bypass:suspended');
    expect(calls, contains('takeBypassReRing'));
  });

  testWidgets('a ring nothing stamped is the deadline', (tester) async {
    expect(await ringReasonAfterOneTick(tester), 'deadline:bathroomIn');
  });
}
