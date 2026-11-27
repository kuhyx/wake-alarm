import 'package:http/http.dart' as http;
import 'package:wake_alarm_sync/services/alarm_arming.dart';
import 'package:wake_alarm_sync/services/alarm_scheduler.dart';
import 'package:wake_alarm_sync/services/alarm_sync_service.dart';
import 'package:wake_alarm_sync/services/firebase_backend.dart';
import 'package:wake_alarm_sync/services/settings_sync.dart';
import 'package:wake_alarm_sync/services/sync_settings.dart';

/// Publishes the armed alarm to the PC and arms the phone's own alarm.
///
/// Split out of `home_screen.dart` for the 250-line gate, and because none of
/// this is UI: it returns a message for the screen to render rather than
/// calling `setState` itself, which also makes it testable without a widget.
///
/// Offline-first: the local half — storing the time and arming the phone —
/// always runs. The sync half degrades to a status line, and the next
/// publish (app start, settings return, an earlier tap) retries it.
class AlarmPublisher {
  /// Creates a publisher; [arming] is injectable for tests.
  AlarmPublisher({AlarmArming? arming})
    : arming = arming ?? AlarmArming(AlarmScheduler());

  /// Bridge that arms the phone's own alarm.
  final AlarmArming arming;

  /// Publishes [hour]:[minute] and arms the alarm, returning a status line.
  ///
  /// Never throws: this runs unattended from the app's init seam, so a sync
  /// failure must degrade to a message rather than take the screen down.
  Future<String> publish({
    required AlarmSyncService? service,
    required int hour,
    required int minute,
    http.Client? httpClient,
  }) async {
    // The local half first: store the time (when a store exists) and arm the
    // phone. Neither depends on a backend or the network, so the alarm is set
    // even on a plane — the sync status below is the only thing that cannot
    // complete offline.
    String? armProblem;
    var inClock = false;
    Exception? saveError;
    if (service != null) {
      try {
        await service.setLocal(hour, minute);
      } on Exception catch (e) {
        // The log could not be written, so the PC must not be told
        // "synced": pushing now would publish the previous time.
        saveError = e;
      }
    }
    try {
      armProblem = await arming.arm(hour, minute);
      if (armProblem == null) {
        inClock = await arming.registerWithClockApp(hour, minute);
      }
    } on Exception catch (e) {
      armProblem ??= 'Error: $e';
    }

    if (saveError != null) {
      return armProblem ?? '${armedFor(hour, minute)}Error: $saveError';
    }

    // The sync half: stage the settings that ride on the record, push, take
    // the winners back into prefs (how a fresh install gets its tags).
    if (service != null) {
      final settings = await SyncSettings.load();
      // syncBackend() falls back to GitHub alone, or pushes to Firebase alone
      // via the mirror, so either credential is enough to proceed.
      final configured = settings.isConfigured || await loadAccount() != null;
      if (configured) {
        try {
          await stageLocalSettings(service);
          await service.push(settings.token, httpClient: httpClient);
          await applySyncedSettings(service);
        } on Exception catch (e) {
          // The local save and the arming are already done; only the push
          // failed. Say so — the time is not lost, it rides the next publish.
          return armProblem ??
              '${armedFor(hour, minute)}Saved locally — will sync to PC. '
                  'Error: $e';
        }
      } else {
        return armProblem ??
            '${armedFor(hour, minute)}'
                'Connect a sync backend in Settings first.';
      }
    } else {
      // Distinct from the "connect a backend" line on purpose. Both used to
      // report the same thing, so a store that failed to open looked like a
      // configuration the user had never done.
      return armProblem ??
          '${armedFor(hour, minute)}Sync store unavailable — reopen the app.';
    }
    return armProblem ?? syncedStatus(hour, minute, inClock: inClock);
  }
}

/// The "Armed for HH:MM." prefix every status line shares: the local arm is
/// what succeeded, whatever the sync half reports.
String armedFor(int hour, int minute) =>
    'Armed for '
    '${hour.toString().padLeft(2, '0')}:'
    '${minute.toString().padLeft(2, '0')}. ';

/// The success line, naming the armed time; names the Clock app only when
/// the handoff to it completed before its timeout, so a silent timeout
/// never claims it.
String syncedStatus(int hour, int minute, {required bool inClock}) {
  final synced = '${armedFor(hour, minute)}Synced to PC ✓';
  return inClock ? '$synced Clock app set ✓' : synced;
}
