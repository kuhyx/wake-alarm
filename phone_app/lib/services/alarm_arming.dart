import 'package:android_intent_plus/android_intent.dart';
import 'package:wake_alarm_sync/services/alarm_scheduler.dart';

/// Arms the phone's own alarm for a chosen time (item 1: no user interaction).
///
/// Split out of `home_screen.dart` to keep that file under the 250-line gate,
/// and because "what it takes to arm an alarm" is its own concern from "the
/// picker UI".
class AlarmArming {
  /// Creates an armer over [scheduler].
  const AlarmArming(this.scheduler);

  /// Platform bridge to the Kotlin scheduler.
  final AlarmScheduler scheduler;

  /// Arms the alarm for [hour]:[minute].
  ///
  /// Returns an error string when it could not be armed, or null on success.
  /// A revoked full-screen-intent grant is a hard failure, not a warning:
  /// without it the alarm posts a notification the sleeping user never sees,
  /// so reporting success would be a lie the user only discovers at 06:00.
  Future<String?> arm(int hour, int minute) async {
    if (!await scheduler.canUseFullScreenIntent()) {
      return 'Allow notifications and "full screen notifications" for this '
          'app in Android settings — without them the alarm cannot show '
          'over the lockscreen.';
    }
    await scheduler.schedule(hour, minute);
    return null;
  }

  /// Also registers the time in the system Clock app, as pure redundancy.
  ///
  /// This used to be the mechanism, and required confirming in another app
  /// every single time. `SKIP_UI` is true because the app has already armed
  /// its own alarm by now, so this must not demand a tap.
  ///
  /// android_intent_plus v5 uses startActivityForResult and the Clock app
  /// never sends a result, so this times out after 3s rather than hang.
  Future<void> registerWithClockApp(int hour, int minute) async {
    final intent = AndroidIntent(
      action: 'android.intent.action.SET_ALARM',
      arguments: <String, Object>{
        'android.intent.extra.alarm.HOUR': hour,
        'android.intent.extra.alarm.MINUTES': minute,
        'android.intent.extra.alarm.SKIP_UI': true,
        'android.intent.extra.alarm.MESSAGE': 'Wake Alarm',
      },
    );
    await intent.launch().timeout(const Duration(seconds: 3), onTimeout: () {});
  }
}
