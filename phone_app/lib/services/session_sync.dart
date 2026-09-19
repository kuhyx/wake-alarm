/// The morning session's tags and history, carried on the synced alarm
/// record next to the ring tags (`settings_sync.dart`).
///
/// Same shape, same reasons: the tags are properties of the flat and must
/// survive a reinstall; the history is what makes a week of mornings
/// judgeable, and it is where diet-guard's PC side reads the weight from.
/// The PC alarm parser ignores every field it does not name, so nothing
/// here can move the alarm time.
library;

import 'package:wake_alarm_sync/services/alarm_sync_service.dart';
import 'package:wake_alarm_sync/services/morning_session.dart';
import 'package:wake_alarm_sync/services/session_json.dart';
import 'package:wake_alarm_sync/services/session_store.dart';
import 'package:wake_alarm_sync/services/session_tag_settings.dart';
import 'package:wake_alarm_sync/services/settings_sync.dart';

/// Field holding the session tag ids, one string per [SessionTagSlot].
const sessionTagsField = 'session_tag_ids';

/// Field holding the last [sessionsCarried] finished sessions, newest first.
const sessionsField = 'morning_sessions';

/// Field holding `{date, kg}` of the newest confirmed weigh-in.
///
/// Redundant with [sessionsField] on purpose: a reader that wants one
/// number (diet-guard's budget) should not have to know the session shape.
const latestWeightField = 'latest_weight_kg';

/// Field holding `{date, level}` of the newest energy tap, for the same
/// reason as [latestWeightField].
const latestEnergyField = 'latest_energy';

/// Field holding the live session while one runs, `{}` once it is over.
///
/// This is how the PC tells "started, not finished" from "never started"
/// and defers the workout lock only while the morning is actually being
/// earned. Kept apart from [sessionsField] because the receiving side
/// merges that one into history, and a live session in history would make
/// `SessionHandoff.afterDismiss` refuse to start the morning it belongs to.
const currentSessionField = 'current_session';

/// How many finished sessions ride on the record.
const sessionsCarried = 14;

/// Copies local session data newer than the log's copy onto the record.
Future<void> stageSessionData(
  AlarmSyncService service, {
  SessionStore? store,
}) async {
  final tags = await SessionTagSettings.load();
  await stageField(
    service,
    sessionTagsField,
    tags.editedAt,
    tags.tagIds,
    configured: tags.isConfigured,
  );
  final sessions = store ?? SessionStore();
  final current = await sessions.loadCurrent();
  final history = await sessions.history();
  if (current != null) {
    await stageField(
      service,
      currentSessionField,
      current.updatedAt.toUtc().toIso8601String(),
      current.toJson(),
      configured: true,
    );
  }
  if (history.isEmpty) return;
  final newest = history
      .map((s) => s.updatedAt)
      .reduce((a, b) => a.isAfter(b) ? a : b);
  final stamp = newest.toUtc().toIso8601String();
  if (current == null) {
    // Cleared with the finish stamp, which is strictly newer than any
    // stamp the live session was staged under (stageField skips on >=).
    await stageField(
      service,
      currentSessionField,
      stamp,
      const <String, Object?>{},
      configured: true,
    );
  }
  await stageField(
    service,
    sessionsField,
    stamp,
    history.take(sessionsCarried).map((s) => s.toJson()).toList(),
    configured: true,
  );
  final weighed = history.where((s) => s.weightKg != null).firstOrNull;
  if (weighed != null) {
    await stageField(service, latestWeightField, stamp, <String, Object?>{
      'date': weighed.date,
      'kg': weighed.weightKg,
    }, configured: true);
  }
  final rated = history.where((s) => s.energy != null).firstOrNull;
  if (rated == null) return;
  await stageField(service, latestEnergyField, stamp, <String, Object?>{
    'date': rated.date,
    'level': rated.energy,
  }, configured: true);
}

/// Writes log values newer than the local copy into local storage.
///
/// Sessions merge per date rather than replace: two installs' mornings end
/// up in one list, and a peer's shorter list cannot truncate ours.
/// [currentSessionField] is deliberately not applied: a live session is
/// never restored from a peer (see the field's doc).
Future<void> applySyncedSessionData(
  AlarmSyncService service, {
  SessionStore? store,
}) async {
  final tags = await SessionTagSettings.load();
  final tagField = service.field(sessionTagsField);
  if (tagField != null && isNewer(tagField.$2, tags.editedAt)) {
    final ids = tagField.$1;
    if (ids is List) {
      await SessionTagSettings.replaceAll(
        ids.whereType<String>().toList(),
        stampOf(tagField.$2),
      );
    }
  }
  final sessions = service.field(sessionsField);
  if (sessions == null) return;
  await (store ?? SessionStore()).mergeHistory(
    SessionStore.decodeSessions(sessions.$1),
  );
}

/// The sessions currently on the record, for tests and diagnostics.
List<MorningSession> sessionsOnRecord(AlarmSyncService service) =>
    SessionStore.decodeSessions(service.field(sessionsField)?.$1);
