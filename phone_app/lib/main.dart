import 'package:flutter/material.dart';

import 'package:wake_alarm_sync/screens/home_screen.dart';
import 'package:wake_alarm_sync/screens/ring_screen.dart';
import 'package:wake_alarm_sync/screens/session_screen.dart';
import 'package:wake_alarm_sync/services/alarm_policy.dart';
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
  // The alarm is not opt-in: launching the app is enough to arm it. There is
  // no "set alarm" button to forget, and no cancel to reach for at 02:00 —
  // AlarmPolicy fixes the time at 08:00 and only ever lets it move earlier.
  final policy = await AlarmPolicy.load();
  await AlarmScheduler().armSchedule(policy.hour, policy.minute);
  runApp(const WakeAlarmSyncApp());
}

/// Root application widget.
class WakeAlarmSyncApp extends StatelessWidget {
  /// Creates a [WakeAlarmSyncApp]; [newScheduler] is the probes' seam.
  const WakeAlarmSyncApp({super.key, this.newScheduler});

  /// Builds the platform bridge for the ring and session screens.
  ///
  /// Null in production (each screen builds the real one). The emulator
  /// harness supplies a file-driven bridge so a machine with no NFC and no
  /// step sensor can still walk the whole morning. A factory rather than an
  /// instance so each screen owns its own, as in production: the NFC
  /// listener's ownership is per instance, and sharing one instance hid the
  /// ring-dispose-wipes-session-listener bug the phone had just shown.
  final AlarmScheduler Function()? newScheduler;

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
        kRingRoute: (_) => RingScreen(scheduler: newScheduler?.call()),
        // Reached by pushReplacement from the ring screen, or as
        // AlarmActivity's initial route when the launcher or the ongoing
        // notification reopens a live session (SessionNotice.kt). Always
        // inside AlarmActivity: NFC reader mode and the kept-on screen live
        // there.
        kSessionRoute: (_) => SessionScreen(scheduler: newScheduler?.call()),
      },
    );
  }
}
