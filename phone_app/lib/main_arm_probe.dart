import 'package:material_ui/material_ui.dart';

import 'package:wake_alarm_sync/main.dart';
import 'package:wake_alarm_sync/services/alarm_scheduler.dart';

/// Debug entrypoint that arms a real alarm a minute out, then shows the app.
///
/// Exercises the true `AlarmManager.setAlarmClock` path — the receiver, the
/// foreground service and the full-screen intent all firing on their own —
/// rather than the `ringNow` shortcut, which skips the scheduler entirely.
/// The offset comes from `--dart-define=ARM_IN_MINUTES`.
///
/// Not part of the shipped app: `flutter build apk` uses `lib/main.dart`.
Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  const offset = int.fromEnvironment('ARM_IN_MINUTES', defaultValue: 1);
  final scheduler = AlarmScheduler();
  final at = DateTime.now().add(const Duration(minutes: offset));
  final fsi = await scheduler.canUseFullScreenIntent();
  // Printed so the harness can read the armed time out of logcat; this is a
  // debug entrypoint, so stdout is the interface.
  // ignore: avoid_print
  print('ARM_PROBE armed=${at.hour}:${at.minute} fsi=$fsi');
  await scheduler.schedule(at.hour, at.minute);
  runApp(const WakeAlarmSyncApp());
}
