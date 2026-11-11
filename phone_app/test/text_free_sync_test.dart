import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sync_settings_ui/sync_settings_ui.dart';
import 'package:wake_alarm_sync/ui/theme.dart';

import 'text_free_support.dart';

/// The Settings sync row opens the shared `sync_settings_ui` screen; it is
/// part of what kuhy sees, so the textgate guard covers it too.
Widget _syncScreen({required bool googleAvailable}) => MaterialApp(
  theme: buildAppTheme(),
  home: SyncSettingsScreen(
    accountLoader: () async => null,
    accountSaver: (_) async {},
    accountClearer: () async {},
    sessionProbe: () async => false,
    firebaseFactory: () async => null,
    googleFirebaseFactory: () async => null,
    googleAvailable: googleAvailable,
  ),
);

void main() {
  for (final google in [true, false]) {
    testWidgets('SyncSettingsScreen (google: $google) has no words', (
      tester,
    ) async {
      phoneView(tester);
      await tester.pumpWidget(_syncScreen(googleAvailable: google));
      await tester.pumpAndSettle();
      expectNoWords(tester, 'SyncSettingsScreen');
    });
  }

  testWidgets('SyncSettingsScreen expanded password form has no words', (
    tester,
  ) async {
    phoneView(tester);
    await tester.pumpWidget(_syncScreen(googleAvailable: false));
    await tester.pumpAndSettle();
    await tester.tap(find.byType(ExpansionTile));
    await tester.pumpAndSettle();
    expect(find.byType(TextField), findsWidgets);
    expectNoWords(tester, 'SyncSettingsScreen-expanded');
  });
}
