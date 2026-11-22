import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:wake_alarm_sync/screens/free_days_screen.dart';
import 'package:wake_alarm_sync/screens/settings_screen.dart'
    show SettingsScreen;
import 'package:wake_alarm_sync/services/free_day_sync.dart';
import 'package:wake_alarm_sync/ui/theme.dart';

void main() {
  testWidgets('settings export/import have one-word tooltips', (tester) async {
    await tester.pumpWidget(
      MaterialApp(theme: buildAppTheme(), home: const SettingsScreen()),
    );

    expect(find.byTooltip('Export'), findsOneWidget);
    expect(find.byTooltip('Import'), findsOneWidget);
  });

  testWidgets('free days sync has one-word tooltip', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: buildAppTheme(),
        home: FreeDaysScreen(
          openPool: () async => throw Exception('test'),
          syncer: FreeDaySync(),
        ),
      ),
    );

    expect(find.byTooltip('Sync'), findsOneWidget);
  });
}
