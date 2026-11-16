// ignore: deprecated_member_use, the dialog under test is framework material.
import 'package:flutter/material.dart' as fw show AlertDialog;
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:wake_alarm_sync/main.dart';
import 'package:wake_alarm_sync/screens/settings_screen.dart';

/// crdt_sync_flutter's passphrase dialog uses the framework's material
/// `showDialog`, which needs the framework's MaterialLocalizations. The
/// app's MaterialApp comes from material_ui and does not supply them.
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
    expect(find.byType(fw.AlertDialog), findsOneWidget);
    expect(find.byType(EditableText), findsOneWidget);
  });
}
