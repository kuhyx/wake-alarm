import 'package:flutter/material.dart';

import 'package:wake_alarm_sync/screens/home_screen.dart';
import 'package:wake_alarm_sync/ui/theme.dart';

/// Entry point.
void main() => runApp(const WakeAlarmSyncApp());

/// Root application widget.
class WakeAlarmSyncApp extends StatelessWidget {
  /// Creates a [WakeAlarmSyncApp].
  const WakeAlarmSyncApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Wake Alarm Sync',
      theme: buildAppTheme(),
      home: const HomeScreen(),
    );
  }
}
