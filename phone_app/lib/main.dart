import 'package:flutter/material.dart';

import 'package:wake_alarm_sync/screens/home_screen.dart';
import 'package:wake_alarm_sync/screens/ring_screen.dart';
import 'package:wake_alarm_sync/services/alarm_scheduler.dart';
import 'package:wake_alarm_sync/ui/theme.dart';

/// Route the Kotlin `AlarmActivity` hands to the engine as its initial
/// route.
const String kRingRoute = '/ring';

/// Navigator key, so the platform side can drive navigation without a context.
final GlobalKey<NavigatorState> navigatorKey = GlobalKey<NavigatorState>();

/// Entry point.
///
/// `ensureInitialized` is required before any MethodChannel call: the
/// startup re-arm below runs before the first frame.
Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // The log store has no change stream, so the picker's save is the only other
  // arm hook. Without this, restarting the app without touching the picker
  // would leave nothing armed at all.
  await AlarmScheduler().rearm();
  runApp(const WakeAlarmSyncApp());
}

/// Root application widget.
class WakeAlarmSyncApp extends StatelessWidget {
  /// Creates a [WakeAlarmSyncApp].
  const WakeAlarmSyncApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Wake Alarm Sync',
      theme: buildAppTheme(),
      navigatorKey: navigatorKey,
      // AlarmActivity sets its initial route to kRingRoute, so the ring screen
      // is what comes up over the lockscreen; the launcher still gets home.
      routes: <String, WidgetBuilder>{
        '/': (_) => const HomeScreen(),
        kRingRoute: (_) => const RingScreen(),
      },
    );
  }
}
