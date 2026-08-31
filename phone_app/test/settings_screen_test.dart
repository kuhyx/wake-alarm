import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wake_alarm_sync/screens/github_mirror_screen.dart';
import 'package:wake_alarm_sync/screens/settings_screen.dart';

void main() {
  testWidgets('shows the two sync links and navigates to each', (
    tester,
  ) async {
    await tester.pumpWidget(
      const MaterialApp(home: SettingsScreen()),
    );

    expect(find.text('Sync settings'), findsOneWidget);
    expect(find.text('Advanced sync (GitHub)'), findsOneWidget);
    expect(find.text('Room proof'), findsOneWidget);
    expect(find.text('Home location'), findsOneWidget);

    await tester.tap(find.text('Advanced sync (GitHub)'));
    await tester.pumpAndSettle();

    expect(find.byType(GitHubMirrorScreen), findsOneWidget);
  });
}
