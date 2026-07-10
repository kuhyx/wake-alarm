import 'package:flutter/material.dart';

import 'package:wake_alarm_sync/screens/home_screen.dart';

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
      theme: ThemeData.dark(useMaterial3: true).copyWith(
        colorScheme: ColorScheme.fromSeed(
          seedColor: Colors.orange,
          brightness: Brightness.dark,
        ),
      ),
      home: const HomeScreen(),
    );
  }
}
