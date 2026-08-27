import 'package:wake_alarm_sync/services/alarm_arming.dart';
import 'package:wake_alarm_sync/services/alarm_scheduler.dart';
import 'package:wake_alarm_sync/services/alarm_sync_service.dart';
import 'package:wake_alarm_sync/services/firebase_backend.dart';
import 'package:wake_alarm_sync/services/sync_settings.dart';

/// Publishes the armed alarm to the PC and arms the phone's own alarm.
///
/// Split out of `home_screen.dart` for the 250-line gate, and because none of
/// this is UI: it returns a message for the screen to render rather than
/// calling `setState` itself, which also makes it testable without a widget.
class AlarmPublisher {
  /// Creates a publisher; [arming] is injectable for tests.
  AlarmPublisher({AlarmArming? arming})
    : arming = arming ?? AlarmArming(AlarmScheduler());

  /// Bridge that arms the phone's own alarm.
  final AlarmArming arming;

  /// Publishes [hour]:[minute] and arms the alarm, returning a status line.
  ///
  /// Never throws: this runs unattended from the app's init seam, so a sync
  /// failure must degrade to a message rather than take the screen down. The
  /// alarm itself is already armed by `main()` regardless of what happens
  /// here — publishing is how the PC learns the time, not how the phone rings.
  Future<String> publish({
    required AlarmSyncService? service,
    required int hour,
    required int minute,
  }) async {
    final settings = await SyncSettings.load();
    // syncBackend() falls back to GitHub alone, or pushes to Firebase alone
    // via the mirror, so either credential is enough to proceed.
    final hasFirebase = await loadAccount() != null;
    if ((!settings.isConfigured && !hasFirebase) || service == null) {
      return 'Connect a sync backend in Settings first.';
    }
    try {
      await service.setLocal(hour, minute);
      await service.push(settings.token);
      final problem = await arming.arm(hour, minute);
      if (problem != null) return problem;
      await arming.registerWithClockApp(hour, minute);
      return 'Synced to PC ✓';
    } on Exception catch (e) {
      return 'Error: $e';
    }
  }
}
