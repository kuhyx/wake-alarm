import 'package:flutter/material.dart';

import 'package:wake_alarm_sync/main.dart';
import 'package:wake_alarm_sync/services/alarm_scheduler.dart';

/// Debug entrypoint that starts the ring and opens the real dismiss route.
///
/// Used to exercise the Kotlin foreground-service and full-screen-intent path
/// on an emulator, where the normal flow needs a sync backend first. It runs
/// the **real** app widget and pushes [kRingRoute], so what appears is exactly
/// what AlarmActivity's initial route produces — a probe with its own UI would
/// prove nothing about the route.
///
/// Not part of the shipped app: `flutter build apk` uses `lib/main.dart`.
Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await AlarmScheduler().ringNow();
  runApp(const WakeAlarmSyncApp());
  WidgetsBinding.instance.addPostFrameCallback((_) {
    navigatorKey.currentState?.pushNamed(kRingRoute);
  });
}
