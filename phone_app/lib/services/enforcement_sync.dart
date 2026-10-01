/// The wake-enforcement fields on the synced alarm record
/// (`DOCS-wake-enforcement.md`, "Firebase -- fields on the phone's
/// alarm.json").
///
/// Staged on every sync through the same [stageField] pattern as the
/// session data, each under a stable stamp (the newest entry's own `at`, or
/// the stick's `updatedAt`) so an unchanged value is never re-pushed. The PC
/// alarm parser ignores every field it does not name.
library;

import 'dart:developer' as developer;

import 'package:wake_alarm_sync/services/alarm_sync_service.dart';
import 'package:wake_alarm_sync/services/enforcement_bridge.dart';
import 'package:wake_alarm_sync/services/escape_log.dart';
import 'package:wake_alarm_sync/services/ring_started_store.dart';
import 'package:wake_alarm_sync/services/settings_sync.dart';

/// `{"date", "at"}` of today's first ring-screen open.
const ringStartedField = 'ring_started';

/// Escape-hatch uses, newest first, at most [EscapeLog.carried].
const escapesField = 'escapes';

/// `{"streak", "locked_through", "last_miss"}`.
const stickStateField = 'stick_state';

/// The phone event log, newest first.
const phoneEventsField = 'phone_events';

/// At most this many events ride on the record...
const eventsCarried = 400;

/// ...and none older than this.
const eventsMaxAge = Duration(days: 14);

/// Stages every enforcement field newer than the record's copy.
///
/// The Dart-held records go first and need no platform; the native ones
/// (stick, event log) are skipped when the channel is absent, as under a
/// widget test or the desktop, rather than failing the whole sync.
Future<void> stageEnforcementData(
  AlarmSyncService service, {
  EnforcementBridge? bridge,
  DateTime Function()? now,
}) async {
  final ring = await RingStartedStore.load();
  final ringAt = ring?['at'];
  if (ring != null && ringAt is String) {
    await stageField(service, ringStartedField, ringAt, ring, configured: true);
  }
  final escapes = await EscapeLog.load();
  final escapeAt = escapes.firstOrNull?['at'];
  if (escapeAt is String) {
    await stageField(
      service,
      escapesField,
      escapeAt,
      escapes,
      configured: true,
    );
  }
  final native = bridge ?? EnforcementBridge();
  try {
    final state = await native.state();
    final stamp = state?.updatedAt;
    if (state != null && stamp != null) {
      final json = state.toStickStateJson();
      await stageField(service, stickStateField, stamp, json, configured: true);
    }
    final events = boundEvents(
      await native.readEvents(),
      (now ?? DateTime.now)(),
    );
    final eventAt = events.firstOrNull?['at'];
    if (eventAt is String) {
      await stageField(
        service,
        phoneEventsField,
        eventAt,
        events,
        configured: true,
      );
    }
  } on Object catch (e) {
    // No native side here: MissingPluginException under a widget test, a
    // FlutterError with no binding at all under a plain unit test. Either
    // way the sync itself must go on.
    developer.log('enforcement fields skipped: $e', name: 'WakeAlarmSync');
  }
}

/// [events] cut to the contract's bounds: newest first, at most
/// [eventsCarried], none older than [eventsMaxAge] before [now]. An entry
/// whose `at` does not parse is dropped -- it could never be placed on a
/// timeline anyway.
List<Map<String, Object?>> boundEvents(
  List<Map<String, Object?>> events,
  DateTime now,
) {
  final cutoff = now.subtract(eventsMaxAge);
  final dated = <(DateTime, Map<String, Object?>)>[
    for (final event in events)
      if (DateTime.tryParse('${event['at']}') case final at?
          when at.isAfter(cutoff))
        (at, event),
  ]..sort((a, b) => b.$1.compareTo(a.$1));
  return [for (final (_, event) in dated.take(eventsCarried)) event];
}
