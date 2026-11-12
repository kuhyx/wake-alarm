import 'package:material_ui/material_ui.dart';

import 'package:wake_alarm_sync/main.dart';
import 'package:wake_alarm_sync/services/alarm_scheduler.dart';

/// Debug entrypoint that starts the ring exactly as a real alarm would.
///
/// Calls `ringNow`, which starts AlarmService — the service then posts its
/// full-screen intent and the system launches AlarmActivity on top. This
/// process then finishes itself, so the picker never sits in front of the
/// ring screen: it used to, and AlarmActivity's pause tore NFC reader mode
/// down with it, which is precisely the bug this probe now has to avoid
/// reintroducing.
///
/// Not part of the shipped app: `flutter build apk` uses `lib/main.dart`.
Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await AlarmScheduler().ringNow();
  // Nothing to show: the ring screen is a separate activity launched by the
  // service. Rendering the picker here would cover it.
  runApp(const WakeAlarmSyncApp());
}
