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
  final history = await (store ?? SessionStore()).history();
  if (history.isEmpty) return;
  final newest = history
      .map((s) => s.updatedAt)
      .reduce((a, b) => a.isAfter(b) ? a : b);
  final stamp = newest.toUtc().toIso8601String();
  await stageField(
    service,
    sessionsField,
    stamp,
    history.take(sessionsCarried).map((s) => s.toJson()).toList(),
    configured: true,
  );
  final weighed = history.where((s) => s.weightKg != null).firstOrNull;
  if (weighed == null) return;
  await stageField(service, latestWeightField, stamp, <String, Object?>{
    'date': weighed.date,
    'kg': weighed.weightKg,
  }, configured: true);
}

/// Writes log values newer than the local copy into local storage.
///
/// Sessions merge per date rather than replace: two installs' mornings end
/// up in one list, and a peer's shorter list cannot truncate ours.
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
