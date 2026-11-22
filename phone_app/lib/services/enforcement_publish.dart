/// Pushes the enforcement fields now, not at the next sync.
///
/// Two moments need it (2026-11-22): a bypass (the app paused, its admin
/// removed, a permission revoked, the ring killed), which the native side
/// records and then starts `publishNowMain` for, and a completed dismiss.
/// The PC rings for a bypass until it reads a `dismissed` newer than it, so
/// both have to reach Firebase within a poll, not minutes later.
library;

import 'dart:developer' as developer;
import 'dart:ui' show DartPluginRegistrant;

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:wake_alarm_sync/services/alarm_sync_service.dart';
import 'package:wake_alarm_sync/services/enforcement_sync.dart';
import 'package:wake_alarm_sync/services/firebase_backend.dart';
import 'package:wake_alarm_sync/services/headless_ring_start.dart';
import 'package:wake_alarm_sync/services/sync_settings.dart';

/// Stages the enforcement fields (the event log included) and pushes.
///
/// Returns whether the push reached a backend. Never throws: the caller is
/// a ring or a dismiss, and neither may wait on a broken network.
Future<bool> publishEnforcementNow({
  Future<AlarmSyncService> Function()? open,
  Future<void> Function(AlarmSyncService service, String token)? push,
}) async {
  try {
    final settings = await SyncSettings.load();
    final hasFirebase = await loadAccount() != null;
    if (!settings.isConfigured && !hasFirebase) {
      debugPrint('WakeAlarmPublish: no sync backend');
      return false;
    }
    final service = await (open ?? AlarmSyncService.open)();
    await stageEnforcementData(service);
    await (push ?? ((s, token) => s.push(token)))(service, settings.token);
    debugPrint('WakeAlarmPublish: pushed');
    return true;
  } on Object catch (e) {
    debugPrint('WakeAlarmPublish: not pushed: $e');
    return false;
  }
}

/// The `publishNowMain` engine's whole job: publish, then say done.
Future<void> runHeadlessPublish({
  Future<bool> Function()? publish,
  MethodChannel? channel,
}) async {
  WidgetsFlutterBinding.ensureInitialized();
  DartPluginRegistrant.ensureInitialized();
  try {
    await (publish ?? publishEnforcementNow)();
  } finally {
    try {
      await (channel ?? const MethodChannel(headlessChannelName))
          .invokeMethod<void>('done');
    } on Object catch (e) {
      developer.log('headless done not delivered: $e', name: 'WakeAlarmRing');
    }
  }
}
