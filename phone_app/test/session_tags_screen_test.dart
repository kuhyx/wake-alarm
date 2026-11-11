import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:wake_alarm_sync/screens/session_tags_screen.dart';
import 'package:wake_alarm_sync/services/alarm_scheduler.dart';
import 'package:wake_alarm_sync/services/session_tag_settings.dart';
import 'package:wake_alarm_sync/ui/cues.dart';
import 'package:wake_alarm_sync/ui/dashed_slot.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late List<String> calls;
  var nfcStarts = true;

  setUp(() {
    calls = <String>[];
    nfcStarts = true;
    SharedPreferences.setMockInitialValues(<String, Object>{});
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
          const MethodChannel(AlarmScheduler.channelName),
          (call) async {
            calls.add(call.method);
            if (call.method == 'startTagRegistration') return nfcStarts;
            return null;
          },
        );
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
    await tester.pump();
  }

  testWidgets('shows the three rooms unregistered on a fresh install', (
    tester,
  ) async {
    await tester.pumpWidget(const MaterialApp(home: SessionTagsScreen()));
    await tester.pump();
    expect(find.byType(DashedSlot), findsNWidgets(3));
  });

  testWidgets('a scan registers the tag in its slot', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: SessionTagsScreen()));
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey<String>('register-wardrobe')));
    await tester.pump();

    // Busy indicator in the button
    final registerBtn = tester.widget<FilledButton>(
      find.byKey(const ValueKey<String>('register-wardrobe')),
    );
    expect(registerBtn.child, isA<SizedBox>());

    expect(find.byType(StatusCue), findsOneWidget);
    final busyCue = tester.widget<StatusCue>(find.byType(StatusCue));
    expect(busyCue.resolvedKind, CueKind.busy);

    await tapTag(tester, 'w1');
    expect(find.text('w1'), findsOneWidget);
    final okCue = tester.widget<StatusCue>(find.byType(StatusCue));
    expect(okCue.semanticLabel, 'The wardrobe tag is registered.');
    expect(calls, contains('stopTagRegistration'));
    expect(
      (await SessionTagSettings.load()).tagAt(SessionTagSlot.wardrobe),
      'w1',
    );
  });

  testWidgets('one tag cannot hold two rooms', (tester) async {
    await SessionTagSettings.saveTagAt(SessionTagSlot.bathroom, 'b1');
    await tester.pumpWidget(const MaterialApp(home: SessionTagsScreen()));
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey<String>('register-desk')));
    await tester.pump();
    await tapTag(tester, 'b1');
    final errCue = tester.widget<StatusCue>(find.byType(StatusCue));
    expect(errCue.semanticLabel, contains('already the bathroom tag'));
    expect(
      (await SessionTagSettings.load()).tagAt(SessionTagSlot.desk),
      isNull,
    );
  });

  testWidgets('re-registering the same room again is fine', (tester) async {
    await SessionTagSettings.saveTagAt(SessionTagSlot.desk, 'd1');
    await tester.pumpWidget(const MaterialApp(home: SessionTagsScreen()));
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey<String>('register-desk')));
    await tester.pump();
    await tapTag(tester, 'd1');
    final okCue = tester.widget<StatusCue>(find.byType(StatusCue));
    expect(okCue.semanticLabel, 'The desk tag is registered.');
  });

  testWidgets('says so when NFC is off', (tester) async {
    nfcStarts = false;
    await tester.pumpWidget(const MaterialApp(home: SessionTagsScreen()));
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey<String>('register-bathroom')));
    await tester.pump();
    final errCue = tester.widget<StatusCue>(find.byType(StatusCue));
    expect(errCue.semanticLabel, contains('NFC is unavailable'));
  });
}
