import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wake_alarm_sync/screens/github_mirror_screen.dart';
import 'package:wake_alarm_sync/screens/settings_screen.dart';
import 'package:wake_alarm_sync/ui/theme.dart';

void main() {
  testWidgets('shows the two sync links and navigates to each', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(theme: buildAppTheme(), home: const SettingsScreen()),
    );

    expect(find.byKey(const Key('settings-sync')), findsOneWidget);
    expect(find.byKey(const Key('settings-github')), findsOneWidget);
    expect(find.byKey(const Key('settings-room-proof')), findsOneWidget);
    expect(find.byKey(const Key('settings-home')), findsOneWidget);

    await tester.tap(find.byKey(const Key('settings-github')));
    await tester.pumpAndSettle();

    expect(find.byType(GitHubMirrorScreen), findsOneWidget);
  });

  testWidgets('export and import are icon-only, labelled, and report back', (
    tester,
  ) async {
    var exported = 0;
    var imported = 0;
    await tester.pumpWidget(
      MaterialApp(
        theme: buildAppTheme(),
        home: SettingsScreen(
          onExport: () async => exported++,
          onImport: () async {
            imported++;
            throw const FormatException('bad file');
          },
        ),
      ),
    );

    await tester.tap(find.byKey(const Key('settings-export')));
    await tester.pump();
    expect(exported, 1);
    expect(find.byIcon(Icons.check_circle), findsOneWidget);

    await tester.tap(find.byKey(const Key('settings-import')));
    await tester.pumpAndSettle(const Duration(seconds: 5));
    expect(imported, 1);
    expect(find.byIcon(Icons.error_outline), findsOneWidget);
  });

  testWidgets('a successful import shows the check icon', (tester) async {
    var imported = 0;
    await tester.pumpWidget(
      MaterialApp(
        theme: buildAppTheme(),
        home: SettingsScreen(
          onImport: () async {
            imported++;
            return true;
          },
        ),
      ),
    );

    await tester.tap(find.byKey(const Key('settings-import')));
    await tester.pump();
    expect(imported, 1);
    expect(find.byIcon(Icons.check_circle), findsOneWidget);
  });

  testWidgets('a cancelled import shows no feedback', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: buildAppTheme(),
        home: SettingsScreen(onImport: () async => false),
      ),
    );

    await tester.tap(find.byKey(const Key('settings-import')));
    await tester.pump();
    expect(find.byType(SnackBar), findsNothing);
  });

  testWidgets('import feedback replaces a still-visible export one', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: buildAppTheme(),
        home: SettingsScreen(
          onExport: () async {},
          onImport: () async => throw const FormatException('bad file'),
        ),
      ),
    );

    await tester.tap(find.byKey(const Key('settings-export')));
    await tester.pump();
    await tester.tap(find.byKey(const Key('settings-import')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 600));
    expect(find.byIcon(Icons.error_outline), findsOneWidget);
    expect(find.byIcon(Icons.check_circle), findsNothing);
  });
}
