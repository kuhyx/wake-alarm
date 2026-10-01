import 'dart:developer' as developer;

import 'package:wake_alarm_sync/services/alarm_sync_service.dart';
import 'package:wake_alarm_sync/services/enforcement_bridge.dart';
import 'package:wake_alarm_sync/services/enforcement_sync.dart';
import 'package:wake_alarm_sync/services/firebase_backend.dart';
import 'package:wake_alarm_sync/services/ring_started_store.dart';
import 'package:wake_alarm_sync/services/sync_settings.dart';

/// Tells the PC the phone is ringing.
///
/// The PC's fallback alarm rings when no `ring_started` for today has
/// arrived by A + 2 min, so this publishes straight away instead of waiting
/// for the next sync. Two sources run it: the headless engine the alarm
/// starts natively (`HeadlessRingStart.kt`, [source] `alarm`) and the ring
/// screen (`ring_screen`) -- the screen does not always open. The first
/// ring of the day wins, and once it has reached the backend the other
/// source does not push again. It never throws and nothing waits on it: a
/// slow or broken network must never stand between the user and the
/// dismiss sequence.
class RingStartRecorder {
  /// Creates a recorder; every dependency is injectable for tests.
  RingStartRecorder({
    EnforcementBridge? bridge,
    Future<AlarmSyncService> Function()? open,
    Future<void> Function(AlarmSyncService service, String token)? push,
    DateTime Function()? now,
    this.openedEvent = 'ring_screen_opened',
    this.source = 'ring_screen',
  }) : _bridge = bridge ?? EnforcementBridge(),
       _open = open ?? AlarmSyncService.open,
       _push = push ?? ((service, token) => service.push(token)),
       _now = now ?? DateTime.now;

  final EnforcementBridge _bridge;
  final Future<AlarmSyncService> Function() _open;
  final Future<void> Function(AlarmSyncService, String) _push;
  final DateTime Function() _now;

  /// Event logged before anything else, or null for none (headless).
  final String? openedEvent;

  /// Which source published, in `ring_started_published`'s data.
  final String source;

  /// Logs the open, records today's start, and publishes it. Never throws.
  ///
  /// Returns whether the publish reached the backend, for tests.
  Future<bool> record() async {
    final opened = openedEvent;
    if (opened != null) {
      try {
        await _bridge.appendEvent(opened);
      } on Object catch (e) {
        _log('$opened not logged: $e');
      }
    }
    try {
      final entry = await RingStartedStore.recordFirst(_now());
      if (await RingStartedStore.publishedOn(entry['date'])) return true;
      final settings = await SyncSettings.load();
      final hasFirebase = await loadAccount() != null;
      if (!settings.isConfigured && !hasFirebase) return false;
      final service = await _open();
      // Only the enforcement fields: the ring is no time to restage tags
      // and history, and the push carries the whole log regardless.
      await stageEnforcementData(service, bridge: _bridge, now: _now);
      await _push(service, settings.token);
      final date = '${entry['date']}';
      await RingStartedStore.markPublished(date);
      await _bridge.appendEvent('ring_started_published', <String, Object?>{
        'date': date,
        'source': source,
      });
      return true;
    } on Object catch (e) {
      _log('ring_started not published: $e');
      return false;
    }
  }

  void _log(String message) => developer.log(message, name: 'WakeAlarmRing');
}
