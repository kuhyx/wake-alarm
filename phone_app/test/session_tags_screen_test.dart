import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:wake_alarm_sync/screens/session_tags_screen.dart';
import 'package:wake_alarm_sync/services/alarm_scheduler.dart';
import 'package:wake_alarm_sync/services/session_tag_settings.dart';

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
    expect(find.textContaining('Bathroom (scale + shower): none'), findsOne);
    expect(find.textContaining('Wardrobe: none'), findsOneWidget);
    expect(find.textContaining('Desk: none'), findsOneWidget);
  });

  testWidgets('a scan registers the tag in its slot', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: SessionTagsScreen()));
    await tester.pump();
    await tester.tap(find.text('Register wardrobe tag'));
    await tester.pump();
    expect(find.text('Waiting for tag…'), findsOneWidget);
    await tapTag(tester, 'w1');
    expect(find.textContaining('Wardrobe: w1'), findsOneWidget);
    expect(find.text('The wardrobe tag is registered.'), findsOneWidget);
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
    await tester.tap(find.text('Register desk tag'));
    await tester.pump();
    await tapTag(tester, 'b1');
    expect(find.textContaining('already the bathroom tag'), findsOneWidget);
    expect(
      (await SessionTagSettings.load()).tagAt(SessionTagSlot.desk),
      isNull,
    );
  });

  testWidgets('re-registering the same room again is fine', (tester) async {
    await SessionTagSettings.saveTagAt(SessionTagSlot.desk, 'd1');
    await tester.pumpWidget(const MaterialApp(home: SessionTagsScreen()));
    await tester.pump();
    await tester.tap(find.text('Register desk tag again'));
    await tester.pump();
    await tapTag(tester, 'd1');
    expect(find.text('The desk tag is registered.'), findsOneWidget);
  });

  testWidgets('says so when NFC is off', (tester) async {
    nfcStarts = false;
    await tester.pumpWidget(const MaterialApp(home: SessionTagsScreen()));
    await tester.pump();
    await tester.tap(find.text('Register bathroom tag'));
    await tester.pump();
    expect(find.textContaining('NFC is unavailable'), findsOneWidget);
  });
}
