import 'dart:developer' as developer;

import 'package:wake_alarm_sync/services/alarm_sync_service.dart';
import 'package:wake_alarm_sync/services/firebase_backend.dart';
import 'package:wake_alarm_sync/services/settings_sync.dart';
import 'package:wake_alarm_sync/services/sync_settings.dart';

/// Pushes the finished session's record to the PC, best effort.
///
/// Runs from the session screen, unattended, at the end of a morning: a
/// backend that is down must not keep the screen up. The home screen's
/// startup publish stages the same history again, so a push that fails here
/// is retried the next time the app is opened.
class SessionPublisher {
  /// Creates a publisher; [open] is injectable for tests.
  SessionPublisher({Future<AlarmSyncService> Function()? open})
    : _open = open ?? AlarmSyncService.open;

  final Future<AlarmSyncService> Function() _open;

  /// Stages and pushes; returns a status line, never throws.
  Future<String> publish() async {
    try {
      final settings = await SyncSettings.load();
      final hasFirebase = await loadAccount() != null;
      if (!settings.isConfigured && !hasFirebase) {
        return 'No sync backend — session kept locally';
      }
      final service = await _open();
      await stageLocalSettings(service);
      await service.push(settings.token);
      await applySyncedSettings(service);
      return 'Session synced to PC ✓';
    } on Exception catch (e, stack) {
      developer.log(
        'session publish failed: $e',
        name: 'WakeAlarmSession',
        error: e,
        stackTrace: stack,
      );
      return 'Session kept locally (sync failed)';
    }
  }
}
