import 'package:flutter/material.dart';

import 'package:wake_alarm_sync/services/alarm_scheduler.dart';

/// Debug entrypoint that starts the ring immediately on launch.
///
/// Used to exercise the Kotlin foreground-service and full-screen-intent path
/// on an emulator, where the normal flow needs a sync backend first. Not part
/// of the shipped app: `flutter build apk` uses `lib/main.dart`.
Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await AlarmScheduler().ringNow();
  runApp(const _Probe());
}

class _Probe extends StatelessWidget {
  const _Probe();

  @override
  Widget build(BuildContext context) => const MaterialApp(
    home: Scaffold(body: Center(child: Text('ring probe'))),
  );
}
