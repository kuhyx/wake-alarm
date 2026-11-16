import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:wake_alarm_sync/main.dart';
import 'package:wake_alarm_sync/screens/settings_screen.dart';

/// crdt_sync_flutter's passphrase dialog (0.8.2 imports material_ui, so it is
/// material_ui's `AlertDialog`) must open from the settings lock icon without
/// a localization exception.
void main() {
  testWidgets('the settings lock icon opens the passphrase dialog', (
    tester,
  ) async {
    await tester.pumpWidget(const WakeAlarmSyncApp());
    navigatorKey.currentState!.push(
      MaterialPageRoute<void>(builder: (_) => const SettingsScreen()),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('settings-e2e')));
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
    expect(find.byType(AlertDialog), findsOneWidget);
    expect(find.byType(EditableText), findsOneWidget);
  });
}
