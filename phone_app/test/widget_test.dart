import 'package:flutter_test/flutter_test.dart';
import 'package:wake_alarm_sync/main.dart';

void main() {
  testWidgets('App renders without crashing', (tester) async {
    await tester.pumpWidget(const WakeAlarmSyncApp());
    expect(find.bySemanticsLabel('Alarm is armed for'), findsOneWidget);
  });
}
