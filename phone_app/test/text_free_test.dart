import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:wake_alarm_sync/screens/escape_dialog.dart';
import 'package:wake_alarm_sync/screens/github_mirror_screen.dart';
import 'package:wake_alarm_sync/screens/home_body.dart';
import 'package:wake_alarm_sync/screens/home_history_card.dart';
import 'package:wake_alarm_sync/screens/home_location_screen.dart';
import 'package:wake_alarm_sync/screens/room_proof_screen.dart';
import 'package:wake_alarm_sync/screens/session_tags_screen.dart';
import 'package:wake_alarm_sync/screens/settings_screen.dart';
import 'package:wake_alarm_sync/screens/stakes_card.dart';
import 'package:wake_alarm_sync/services/alarm_scheduler.dart';
import 'package:wake_alarm_sync/services/room_proof_settings.dart';
import 'package:wake_alarm_sync/services/session_rules.dart';
import 'package:wake_alarm_sync/services/session_store.dart';
import 'package:wake_alarm_sync/services/session_tag_settings.dart';
import 'package:wake_alarm_sync/ui/theme.dart';

import 'fake_enforcement_channel.dart';
import 'text_free_support.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('settings-type screens', () {
    testWidgets('SettingsScreen has no words on screen', (tester) async {
      phoneView(tester);
      SharedPreferences.setMockInitialValues(<String, Object>{});
      await tester.pumpWidget(const MaterialApp(home: SettingsScreen()));
      await tester.pumpAndSettle();
      expectNoWords(tester, 'SettingsScreen');
    });

    testWidgets('HomeBody has no words on screen', (tester) async {
      phoneView(tester);
      FakeEnforcementChannel().install();
      await tester.pumpWidget(
        MaterialApp(
          theme: buildAppTheme(),
          home: Scaffold(
            appBar: AppBar(actions: const [Icon(Icons.settings)]),
            body: HomeBody(
              time: '07:00',
              baseline: '07:30',
              isOverridden: true,
              busy: false,
              status: 'Synced to PC ✓',
              configured: false,
              onPickEarlier: () {},
            ),
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));
      expectNoWords(tester, 'HomeBody');
    });

    testWidgets('RoomProofScreen fresh install has no words', (tester) async {
      phoneView(tester);
      SharedPreferences.setMockInitialValues(<String, Object>{});
      const channel = MethodChannel(AlarmScheduler.channelName);
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(channel, (call) async {
            if (call.method == 'startTagRegistration') return true;
            return null;
          });
      await tester.pumpWidget(const MaterialApp(home: RoomProofScreen()));
      await tester.pumpAndSettle();
      expectNoWords(tester, 'RoomProofScreen-fresh');
    });

    testWidgets('RoomProofScreen with tag registered has no words', (
      tester,
    ) async {
      phoneView(tester);
      SharedPreferences.setMockInitialValues(<String, Object>{});
      await RoomProofSettings.saveNfcTagAt(0, '04a2b3c4');
      const channel = MethodChannel(AlarmScheduler.channelName);
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(channel, (call) async {
            if (call.method == 'startTagRegistration') return true;
            return null;
          });
      await tester.pumpWidget(const MaterialApp(home: RoomProofScreen()));
      await tester.pumpAndSettle();
      expectNoWords(tester, 'RoomProofScreen-tagged');
    });

    testWidgets('SessionTagsScreen has no words on screen', (tester) async {
      phoneView(tester);
      SharedPreferences.setMockInitialValues(<String, Object>{});
      const channel = MethodChannel(AlarmScheduler.channelName);
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(channel, (call) async {
            if (call.method == 'startTagRegistration') return true;
            return null;
          });
      await tester.pumpWidget(const MaterialApp(home: SessionTagsScreen()));
      await tester.pump();
      await tester.pump();
      expectNoWords(tester, 'SessionTagsScreen');
    });

    testWidgets('HomeLocationScreen has no words on screen', (tester) async {
      phoneView(tester);
      SharedPreferences.setMockInitialValues(<String, Object>{});
      const channel = MethodChannel(AlarmScheduler.channelName);
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(channel, (call) async => null);
      await tester.pumpWidget(const MaterialApp(home: HomeLocationScreen()));
      await tester.pump();
      await tester.pump();
      expectNoWords(tester, 'HomeLocationScreen');
    });

    testWidgets('GitHubMirrorScreen has no words on screen', (tester) async {
      phoneView(tester);
      SharedPreferences.setMockInitialValues(<String, Object>{});
      const channel = MethodChannel(AlarmScheduler.channelName);
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(channel, (call) async => null);
      await tester.pumpWidget(
        MaterialApp(theme: buildAppTheme(), home: const GitHubMirrorScreen()),
      );
      await tester.pumpAndSettle();
      expectNoWords(tester, 'GitHubMirrorScreen');
    });

    testWidgets('EscapeDialog has no words on screen', (tester) async {
      phoneView(tester);
      SharedPreferences.setMockInitialValues(<String, Object>{});
      await tester.pumpWidget(
        MaterialApp(
          theme: buildAppTheme(),
          home: Scaffold(
            body: Center(
              child: IconButton(
                key: const Key('open'),
                onPressed: () => showDialog<String>(
                  context: tester.element(find.byKey(const Key('open'))),
                  barrierDismissible: false,
                  builder: (_) => const EscapeDialog(),
                ),
                icon: const Icon(Icons.open_in_new),
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.byKey(const Key('open')));
      await tester.pumpAndSettle();
      expectNoWords(tester, 'EscapeDialog');
    });

    testWidgets('HomeHistoryCard has no words on screen', (tester) async {
      phoneView(tester);
      SharedPreferences.setMockInitialValues(<String, Object>{});
      final store = SessionStore();
      for (var day = 1; day <= 9; day++) {
        await store.archive(
          SessionRules.start(
            now: DateTime(2026, 9, day, 8),
            tags: const SessionTagSettings(),
            nfcAvailable: false,
          )..weightKg = 70.0 + day,
        );
      }
      // As the home tile shows it: a scrolling bottom sheet.
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(body: SingleChildScrollView(child: HomeHistoryCard())),
        ),
      );
      await tester.pump();
      expectNoWords(tester, 'HomeHistoryCard');
    });

    testWidgets('StakesCard has no words on screen', (tester) async {
      phoneView(tester);
      SharedPreferences.setMockInitialValues(<String, Object>{});
      FakeEnforcementChannel()
        ..install()
        ..state = nativeState(streak: 1, lockedThrough: '2026-10-02');
      final thursday = DateTime(2026, 10, 1, 6, 50);
      var escaped = 0;
      await tester.pumpWidget(
        MaterialApp(
          theme: buildAppTheme(),
          home: Scaffold(
            body: SingleChildScrollView(
              child: StakesCard(
                now: () => thursday,
                nextAlarm: () async => (hour: 6, minute: 59),
                onEscaped: () => escaped++,
              ),
            ),
          ),
        ),
      );
      await tester.pump();
      expectNoWords(tester, 'StakesCard');
    });
  });
}
